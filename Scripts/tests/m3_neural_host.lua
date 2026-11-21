-- Isolated GitHub REAPER host observation; no policy or installed change.
local base=reaper.GetResourcePath()
local cfg=dofile(base..'/host_config.lua')
local out=cfg.output
local failures={}
local metrics={}
local finished=false
local track,fx
local started=reaper.time_precise()
local phase='startup'
local phase_started=started
reaper.gmem_attach('m3_neural_host_v1')
local function write(path,text)
  local f=assert(io.open(path,'w'));f:write(text);f:close()
end
local function log(text)
  local f=assert(io.open(out..'/phase.log','a'))
  f:write(string.format('%.6f\t%s\n',reaper.time_precise()-started,text));f:close()
end
local function check(ok,name)
  if not ok then failures[#failures+1]=name;log('FAIL '..name) end
  return ok
end
local function param(name)
  for p=0,reaper.TrackFX_GetNumParams(track,fx)-1 do
    local ok,n=reaper.TrackFX_GetParamName(track,fx,p,'')
    if ok and n==name then return p end
  end
  error('Parameter unavailable: '..name)
end
local function set(name,value)
  return reaper.TrackFX_SetParamNormalized(track,fx,param(name),value)
end
local function get(name)
  return reaper.TrackFX_GetParamNormalized(track,fx,param(name))
end
local function near(a,b) return math.abs(a-b)<0.00001 end
local function audio_info()
  metrics.audio_running=reaper.Audio_IsRunning()
  metrics.play_state=reaper.GetPlayState()
  metrics.play_position=reaper.GetPlayPosition()
  for _,key in ipairs({'MODE','IDENT_IN','IDENT_OUT','BSIZE','SRATE','BPS'}) do
    local ok,value=reaper.GetAudioDeviceInfo(key)
    metrics['audio_'..key:lower()]=ok and value or 'unavailable'
  end
end
local function finish()
  if finished then return end
  finished=true
  audio_info()
  metrics.elapsed_seconds=reaper.time_precise()-started
  metrics.failure_count=#failures
  metrics.final_active=reaper.gmem_read(20)
  for _,v in ipairs({{'sample_rate',2},{'block_size',3},{'processed_samples',4},
    {'blocks',5},{'input_peak',6},{'recorded_samples',7},{'max_block',8},
    {'event_count',10},{'overflow',11},{'dry_max_error',12},{'dry_samples',13},
    {'nonfinite',14},{'output_peak',15},{'dry_changed_samples',17},
    {'last_recorded_sample',21},{'recording_discontinuities',22}}) do
    metrics[v[1]]=reaper.gmem_read(v[2])
  end
  local lines={'metric\tvalue'}
  for k,v in pairs(metrics) do lines[#lines+1]=k..'\t'..tostring(v) end
  write(out..'/metrics.tsv',table.concat(lines,'\n')..'\n')
  write(out..'/failures.txt',table.concat(failures,'\n'))
  local ev={'phase\tsample\toffset\tstatus\tnote\tvelocity'}
  for n=0,math.min(32768,reaper.gmem_read(10))-1 do
    local row={}
    for c=0,5 do row[#row+1]=string.format('%.0f',reaper.gmem_read(16384+n*6+c)) end
    ev[#ev+1]=table.concat(row,'\t')
  end
  write(out..'/events.tsv',table.concat(ev,'\n')..'\n')
  reaper.gmem_write(0,0)
  reaper.OnStopButton()
  log('finished')
  reaper.GetSetProjectInfo(0,'DIRTY',0,true)
  reaper.defer(function() reaper.Main_OnCommand(40004,0) end)
end
local function setup()
  log('script-start '..reaper.GetAppVersion())
  metrics.reaper_version=reaper.GetAppVersion()
  reaper.OnStopButton()
  reaper.GetSetProjectInfo(0,'PROJECT_SRATE',96000,true)
  reaper.GetSetProjectInfo(0,'PROJECT_SRATE_USE',1,true)
  reaper.InsertTrackAtIndex(0,false)
  track=reaper.GetTrack(0,0)
  reaper.SetMediaTrackInfo_Value(track,'I_PERFFLAGS',3)
  reaper.SetMediaTrackInfo_Value(track,'D_VOL',1)
  local input=reaper.TrackFX_AddByName(track,'JS: m3_neural_host_input',false,-1)
  fx=reaper.TrackFX_AddByName(track,'VST3: M3 Neural Lab (96 kHz)',false,-1)
  local capture=reaper.TrackFX_AddByName(track,'JS: m3_neural_host_capture',false,-1)
  assert(check(input==0 and fx==1 and capture==2,'three-effect-chain'), 'FX chain unavailable')
  metrics.default_gate=get('Quiet input gate')
  metrics.default_threshold=get('Gate threshold')
  check(near(metrics.default_gate,0) and near(metrics.default_threshold,0.5),'default-settings')
  set('Quiet input gate',1);set('Gate threshold',0.6)
  local ok,chunk=reaper.GetTrackStateChunk(track,'',false)
  assert(check(ok and #chunk>0,'save-state'),'Cannot save state')
  set('Quiet input gate',0);set('Gate threshold',0.2)
  assert(check(reaper.SetTrackStateChunk(track,chunk,false),'restore-state'),'Cannot restore state')
  fx=1
  metrics.restored_gate=get('Quiet input gate')
  metrics.restored_threshold=get('Gate threshold')
  check(near(metrics.restored_gate,1) and near(metrics.restored_threshold,0.6),'state-values')
  set('Quiet input gate',0);set('Gate threshold',0.5)
  local source=reaper.PCM_Source_CreateFromFile(cfg.wav)
  assert(source,'Cannot open pinned recording')
  metrics.source_sample_rate=reaper.GetMediaSourceSampleRate(source)
  metrics.source_seconds=reaper.GetMediaSourceLength(source)
  assert(check(metrics.source_sample_rate==96000 and
    near(metrics.source_seconds,cfg.samples/96000),'recording-source'), 'Recording source differs')
  local item=reaper.AddMediaItemToTrack(track)
  local take=reaper.AddTakeToMediaItem(item)
  reaper.SetMediaItemTake_Source(take,source)
  reaper.SetMediaItemInfo_Value(item,'D_POSITION',0)
  reaper.SetMediaItemInfo_Value(item,'D_LENGTH',cfg.samples/96000)
  reaper.SetMediaItemInfo_Value(item,'D_FADEINLEN',0)
  reaper.SetMediaItemInfo_Value(item,'D_FADEOUTLEN',0)
  reaper.UpdateItemInProject(item)
  reaper.UpdateArrange()
  metrics.project_seconds=reaper.GetProjectLength(0)
  assert(check(near(metrics.project_seconds,cfg.samples/96000),'project-length'), 'Project length differs')
  for i=0,32767*6+16390 do reaper.gmem_write(i,0) end
  reaper.gmem_write(31,cfg.samples)
  reaper.SetEditCurPos(0,false,false)
  metrics.audio_running_before_init=reaper.Audio_IsRunning()
  reaper.Audio_Init()
  phase='audio-start';phase_started=reaper.time_precise()
  audio_info()
  log(phase)
end
local function tick()
  if finished then return end
  local now=reaper.time_precise()
  if now-started>180 then check(false,'script-timeout');finish();return end
  if phase=='startup' and now-started>=2 then
    -- Command-line scripts can run before the host finishes opening its first
    -- project. Yield to the UI before creating items or starting transport.
    setup()
  elseif phase=='audio-start' then
    if reaper.Audio_IsRunning()~=0 then
      audio_info()
      metrics.audio_running_at_play=metrics.audio_running
      if not check(tostring(metrics.audio_mode):upper():find('JACK',1,true)~=nil,'jack-backend') then finish();return end
      reaper.gmem_write(0,1)
      metrics.play_start_time=now
      metrics.play_state_before_request=reaper.GetPlayState()
      reaper.OnPlayButtonEx(0)
      metrics.play_state_after_request=reaper.GetPlayState()
      phase='ordinary';phase_started=now;log(phase)
    elseif now-phase_started>10 then
      check(false,'audio-engine-not-running');finish();return
    end
  elseif phase=='ordinary' and now-phase_started>3 and
         (reaper.gmem_read(4)==0 or reaper.GetPlayPosition()<=0) then
    check(false,'audio-callback-or-transport-not-running');finish();return
  elseif phase=='ordinary' and reaper.GetPlayPosition()>=cfg.samples/96000+0.5 then
    metrics.ordinary_wall_seconds=now-metrics.play_start_time
    metrics.ordinary_event_count=reaper.gmem_read(10)
    metrics.eof_active=reaper.gmem_read(20)
    metrics.ordinary_dry_samples=reaper.gmem_read(13)
    -- Full recording is complete. A bounded extra segment supplies real held
    -- output for the explicit Panic check if EOF itself is already silent.
    reaper.gmem_write(0,2)
    if reaper.gmem_read(20)==0 then reaper.SetEditCurPos(10,false,true) end
    phase='await-held';phase_started=now;log(phase)
  elseif phase=='await-held' then
    if reaper.gmem_read(20)>0 then
      metrics.panic_before_active=reaper.gmem_read(20)
      metrics.panic_event_index=reaper.gmem_read(10)
      reaper.gmem_write(30,1) -- silent future input, upstream of the plugin
      reaper.gmem_write(0,3)
      set('Panic',1)
      metrics.panic_parameter=get('Panic')
      phase='panic';phase_started=now;log(phase)
    elseif now-phase_started>12 then
      check(false,'no-held-note-for-panic');finish();return
    end
  elseif phase=='panic' and now-phase_started>1 then
    metrics.panic_after_active=reaper.gmem_read(20)
    check(metrics.panic_after_active==0,'panic-releases')
    -- Hosts can retain their automation value; the observable gate is MIDI.
    finish();return
  end
  reaper.defer(function()
    local ok,err=xpcall(tick,debug.traceback)
    if not ok then check(false,err);finish() end
  end)
end
local ok,err=xpcall(tick,debug.traceback)
if not ok then check(false,err);finish() end
