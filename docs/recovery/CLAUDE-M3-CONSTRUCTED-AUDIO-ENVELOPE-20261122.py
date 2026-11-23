"""POST HOC audio envelope check of the four suppressed NoteOns of constructed labels 112-115 (pitch 51). Not pre-registered; user asked "run audio tests".
Reads the local constructed recording (int16, 96 kHz), band-passes +-3%% around 155.56 Hz (MIDI 51, A=440), 5 ms mean Hilbert envelope. Run: python3 -P -E this.py from the project root."""
import numpy as np, scipy.io.wavfile as w, scipy.signal as s
p='build/physical-capture/note-combination-corpus-tuning/combinations.wav'
sr,a=w.read(p,mmap=True); print(sr,a.dtype,a.shape)
lo,hi=7142453-96000, 7142453+221000
x=np.asarray(a[lo:hi]).astype(np.float64)
if a.dtype.kind=='i': x/=np.iinfo(a.dtype).max
f=155.56
sos=s.butter(4,[f*0.97,f*1.03],btype='band',fs=sr,output='sos'); y=s.sosfiltfilt(sos,x)
env=np.abs(s.hilbert(y)); ms=int(0.005*sr)
e=np.convolve(env,np.ones(ms)/ms,'same')
for name,smp in [('label start',7142453),('event0',7210303),('event3',7211007),('+50ms',7210303+4800),('+300ms',7210303+28800),('-50ms',7210303-4800),('-300ms',7210303-28800)]:
    print(name, smp, round(float(e[smp-lo]),5))
def rise(c,half):
    seg=e[c-lo-half:c-lo+half]; return float(seg.max()/max(seg.min(),1e-12))
print('env max/min +-20ms of events', round(rise(7210303+350,1920),3))
vals=[rise(7142453+k*4800+2400,2400) for k in range(2,40)]
print('same ratio over 10 ms windows across label: median', round(float(np.median(vals)),3),'max', round(float(max(vals)),3))
# onset-like: largest 20ms rise anywhere in the label
step=1920
r=[e[i+step]/max(e[i],1e-12) for i in range(96000+9600, len(e)-step-9600, 480)]
print('largest 20 ms rise ratio in label', round(max(r),3), 'at ms after start', (96000+9600+480*int(np.argmax(r)))/96-1000)
