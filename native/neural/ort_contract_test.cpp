// Model layout and input-storage checks, using arithmetic ONNX fixtures only.
#include "ort_model.hpp"
#include <cstdlib>
#include <filesystem>
#include <iostream>

namespace {
using namespace m3::neural;
void check(const std::filesystem::path& root,const char* filename,ModelOptions options) {
  const auto path=(root/filename).string();Model model(path.c_str(),options);
  for(const float shift: {0.0F,1.0F/64.0F}) {
    model.window.fill(shift*64.0F);
    auto outputs=model.predict();
    for(std::size_t frame=0;frame<2;++frame) for(std::size_t head=0;head<2;++head) {
      const auto* values=model.readout(outputs,head,frame);
      for(std::size_t pitch=0;pitch<88;++pitch) {
        const float expected=(head ? .5F : 0.0F)+static_cast<float>(164+frame)/(head ? 512.0F : 256.0F)
                             +static_cast<float>(pitch)/65536.0F+shift;
        if(values[pitch]!=expected) throw std::runtime_error("readout or input storage differs");
      }
    }
    for(const auto index: {std::array<std::size_t,2>{2,0},std::array<std::size_t,2>{0,2}}) {
      bool rejected=false;
      try {(void)model.readout(outputs,index[0],index[1]);} catch(const std::runtime_error&) {rejected=true;}
      if(!rejected) throw std::runtime_error("invalid readout index accepted");
    }
  }
}
void reject(const std::filesystem::path& root,const char* filename,ModelOptions options) {
  bool rejected=false;
  try {const auto path=(root/filename).string();Model model(path.c_str(),options);}
  catch(const std::exception&) {rejected=true;}
  if(!rejected) throw std::runtime_error(std::string("invalid contract accepted: ")+filename);
}
}
int main(int argc,char** argv) {
  try {
    if(argc!=2) throw std::runtime_error("usage: neural_ort_contract_test FIXTURES");
    const auto* remote=std::getenv("GITHUB_ACTIONS");
    if(!remote || std::string(remote)!="true") throw std::runtime_error("GitHub-only native adapter test");
    const std::filesystem::path root(argv[1]);
    ModelOptions legacy,old_crop,full,temporal;
    old_crop.cropped_readout=true;
    full.layout=ModelLayout::CorrectedFull;
    temporal.layout=ModelLayout::TemporalReadout;
    check(root,"full.onnx",legacy);check(root,"legacy-crop.onnx",old_crop);
    check(root,"full.onnx",full);check(root,"temporal.onnx",temporal);
    reject(root,"temporal.onnx",legacy);reject(root,"full.onnx",temporal);
    reject(root,"wrong-input.onnx",temporal);reject(root,"wrong-input-shape.onnx",temporal);
    reject(root,"wrong-output-shape.onnx",temporal);
    reject(root,"missing-legacy-metadata.onnx",old_crop);
    auto mixed=temporal;mixed.cropped_readout=true;reject(root,"temporal.onnx",mixed);
    std::cout<<"PASS: four model layouts, readout/input storage, invalid contracts\n";
    return 0;
  } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 2;}
}
