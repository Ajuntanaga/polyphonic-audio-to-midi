// Paired, unpaced numerical check. This is not a component timing measurement.
#include "ort_model.hpp"
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>

namespace {
using namespace m3::neural;
template<class T> std::vector<T> read(const char* path) {
  std::ifstream file(path,std::ios::binary|std::ios::ate);
  if(!file) throw std::runtime_error("cannot open paired input");
  const auto size=file.tellg();
  if(size<=0 || static_cast<std::uint64_t>(size)%sizeof(T)) throw std::runtime_error("invalid paired input size");
  std::vector<T> result(static_cast<std::size_t>(size)/sizeof(T));file.seekg(0);
  file.read(reinterpret_cast<char*>(result.data()),size);
  if(!file) throw std::runtime_error("cannot read paired input");
  return result;
}
bool equal_events(const Batch& a,const Batch& b) {
  if(a.count!=b.count) return false;
  for(std::size_t i=0;i<a.count;++i)
    if(a.events[i].frame!=b.events[i].frame || a.events[i].note!=b.events[i].note || a.events[i].on!=b.events[i].on)
      return false;
  return true;
}
}
int main(int argc,char** argv) {
  try {
    if(argc!=6 && !(argc==7 && std::string(argv[6])=="--corrected"))
      throw std::runtime_error("usage: neural_ort_crop_check MONO.f32 FILTER.f64 ORIGINAL.onnx CROPPED.onnx OUTPUT [--corrected]");
    const bool corrected=argc==7;
    const char* remote=std::getenv("GITHUB_ACTIONS");
    if(!remote || std::string(remote)!="true") throw std::runtime_error("GitHub-only paired crop check");
    const auto audio=read<float>(argv[1]);const auto taps=read<double>(argv[2]);
    if(taps.size()!=kTaps) throw std::runtime_error("unexpected causal filter length");
    std::array<double,kTaps> coefficients{};std::copy(taps.begin(),taps.end(),coefficients.begin());
    Resampler resampler(coefficients);Window window;Decoder reference_decoder,cropped_decoder;
    ModelOptions reference_options,cropped_options;
    if(corrected) {
      reference_options.layout=ModelLayout::CorrectedFull;
      cropped_options.layout=ModelLayout::TemporalReadout;
    } else cropped_options.cropped_readout=true;
    Model reference(argv[3],reference_options);Model cropped(argv[4],cropped_options);
    const std::filesystem::path directory(argv[5]);std::filesystem::create_directories(directory);
    std::ofstream notes(directory/"notes.f32",std::ios::binary),onsets(directory/"onsets.f32",std::ios::binary);
    std::ofstream frames(directory/"frames.tsv");frames<<"frame\tsource_end\n";
    if(!notes || !onsets || !frames) throw std::runtime_error("cannot create paired outputs");
    std::array<double,2> maximum_error{};std::array<float,147> resampled{};
    std::uint64_t windows=0,event_count=0;bool event_identity=true,finite=true,bit_identity=true;
    for(std::size_t offset=0;offset<audio.size();) {
      const auto count=std::min(kBlock,audio.size()-offset);
      const auto produced=resampler.consume(audio.data()+offset,count,resampled);offset+=count;
      window.append(resampled.data(),produced);
      if(!window.ready()) continue;
      window.copy(reference.window.data());cropped.window=reference.window;
      auto original=reference.predict();auto derived=cropped.predict();
      for(std::size_t frame=0;frame<2;++frame) {
        for(std::size_t head=0;head<2;++head) {
          const auto* a=reference.readout(original,head,frame);
          const auto* b=cropped.readout(derived,head,frame);
          bit_identity=bit_identity&&std::memcmp(a,b,kPitches*sizeof(float))==0;
          for(std::size_t pitch=0;pitch<kPitches;++pitch) {
            finite=finite&&std::isfinite(a[pitch])&&std::isfinite(b[pitch]);
            maximum_error[head]=std::max(maximum_error[head],std::abs(static_cast<double>(a[pitch])-b[pitch]));
          }
          auto& stream=head==0?notes:onsets;
          stream.write(reinterpret_cast<const char*>(b),static_cast<std::streamsize>(kPitches*sizeof(float)));
        }
        frames<<cropped_decoder.frame()<<'\t'<<offset<<'\n';
        Batch a{},b{};
        reference_decoder.consume(reference.readout(original,0,frame),reference.readout(original,1,frame),a);
        cropped_decoder.consume(cropped.readout(derived,0,frame),cropped.readout(derived,1,frame),b);
        event_identity=event_identity&&equal_events(a,b);event_count+=b.count;
      }
      ++windows;window.advance();
    }
    notes.close();onsets.close();frames.close();
    if(!notes || !onsets || !frames) throw std::runtime_error("paired output write failed");
    const bool eof_identity=reference_decoder.active()==cropped_decoder.active();
    const bool numerical=corrected ? bit_identity : maximum_error[0]<=1e-5&&maximum_error[1]<=1e-5;
    const bool passed=windows>0&&finite&&event_identity&&eof_identity&&numerical;
    std::ofstream report(directory/"summary.json");
    report<<std::setprecision(17)<<"{\"schema\":\"m3_neural_crop_paired_v1\",\"source_samples\":"<<audio.size()
          <<",\"corrected_temporal_contract\":"<<(corrected?"true":"false")
          <<",\"readouts_bit_identical\":"<<(bit_identity?"true":"false")
          <<",\"windows\":"<<windows<<",\"frames\":"<<cropped_decoder.frame()<<",\"generated_events\":"<<event_count
          <<",\"maximum_note_error\":"<<maximum_error[0]<<",\"maximum_onset_error\":"<<maximum_error[1]
          <<",\"all_finite\":"<<(finite?"true":"false")<<",\"generated_event_identity\":"<<(event_identity?"true":"false")
          <<",\"eof_state_identity\":"<<(eof_identity?"true":"false")<<",\"paired_identity_pass\":"<<(passed?"true":"false")<<"}\n";
    report.close();if(!report) throw std::runtime_error("paired summary write failed");
    std::cout<<"Paired original/cropped readout "<<(passed?"PASS":"FAIL")<<"; windows "<<windows<<'\n';
    return passed?0:2;
  } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 2;}
}
