// Bounded synthetic worker diagnosis; execution is restricted to GitHub Actions.
#include "ort_model.hpp"
#include <cstdlib>
#include <exception>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <thread>

namespace {
using namespace m3::neural;
using Clock=std::chrono::steady_clock;
constexpr std::size_t kCases=32,kCalls=128,kValues=2*172*88;
using Signal=std::array<float,kWindow>;
using Values=std::array<float,kValues>;
std::uint64_t now() {
  return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count());
}
std::vector<Signal> signals() {
  std::vector<Signal> result(kCases);
  constexpr std::array<double,6> hz{82.406889,110.0,146.832384,195.997718,246.941651,329.627557};
  for(std::size_t c=1;c<kCases;++c) for(std::size_t j=0;j<kWindow;++j) {
    const double t=static_cast<double>(j+c*512)/22050.0;
    double sum=0;
    for(std::size_t n=0;n<1+c%6;++n)
      sum+=(0.08/static_cast<double>(n+1))*std::sin(6.283185307179586*hz[n]*t);
    result[c][j]=static_cast<float>(sum*(0.6+0.4*std::sin(3.1*t)));
  }
  return result;
}
struct Result {
  const char* name;int threads;bool construct_on_worker;
  std::uint64_t warmup{};std::vector<std::uint64_t> calls;
  double maximum_error{};bool finite=true;
};
void evaluate(Model& model,const std::vector<Signal>& input,const std::vector<Values>* reference,
              std::vector<Values>* saved,Result& result) {
  result.warmup=model.warmup_ns;result.calls.reserve(kCalls);
  for(std::size_t i=0;i<kCalls;++i) {
    const auto index=i%kCases;model.window=input[index];
    const auto begin=now();auto out=model.predict();result.calls.push_back(now()-begin);
    for(std::size_t head=0;head<2;++head) {
      const float* value=out[head].GetTensorData<float>();
      for(std::size_t k=0;k<172*88;++k) {
        const auto offset=head*172*88+k;
        result.finite=result.finite&&std::isfinite(value[k]);
        if(reference) result.maximum_error=std::max(result.maximum_error,
            std::abs(static_cast<double>(value[k])-(*reference)[index][offset]));
        if(saved&&i<kCases) (*saved)[index][offset]=value[k];
      }
    }
  }
}
void run(const char* path,const std::vector<Signal>& input,const std::vector<Values>* reference,
         std::vector<Values>* saved,Result& result) {
  std::exception_ptr error;std::unique_ptr<Model> model;
  if(!result.construct_on_worker) model=std::make_unique<Model>(path,ModelOptions{result.threads,nullptr});
  std::thread worker([&]{
    try {
      if(result.construct_on_worker) model=std::make_unique<Model>(path,ModelOptions{result.threads,nullptr});
      evaluate(*model,input,reference,saved,result);
    } catch(...) {error=std::current_exception();}
  });
  worker.join();if(error) std::rethrow_exception(error);
}
}
int main(int argc,char** argv) {
  try {
    if(argc!=3) throw std::runtime_error("usage: neural_ort_diagnosis MODEL OUTPUT_DIRECTORY");
    const char* remote=std::getenv("GITHUB_ACTIONS");
    if(!remote||std::string(remote)!="true") throw std::runtime_error("GitHub-only synthetic diagnosis");
    const auto input=signals();std::vector<Values> reference(kCases);
    std::array<Result,4> results{{{"reference_2_main",2,false},{"single_1_main",1,false},
                                {"parallel_4_main",4,false},{"reference_2_worker",2,true}}};
    run(argv[1],input,nullptr,&reference,results[0]);
    for(std::size_t i=1;i<results.size();++i) run(argv[1],input,&reference,nullptr,results[i]);
    const std::string directory=argv[2],prefix=directory+"/ort-profile";
    Model profile(argv[1],ModelOptions{2,prefix.c_str()});
    for(std::size_t i=0;i<8;++i) {profile.window=input[i];auto ignored=profile.predict();(void)ignored;}
    const auto profile_path=profile.finish_profile();
    std::ofstream report(directory+"/measurements.json");
    if(!report) throw std::runtime_error("cannot write diagnosis");
    report<<std::setprecision(17)<<"{\"schema\":\"m3_ort_synthetic_diagnosis_v1\",\"calls_per_case\":"<<kCalls
          <<",\"signals\":"<<kCases<<",\"profile_path\":\""<<profile_path<<"\",\"cases\":[";
    bool success=true;
    for(std::size_t j=0;j<results.size();++j) {
      const auto& r=results[j];if(j) report<<',';
      report<<"{\"name\":\""<<r.name<<"\",\"intra_threads\":"<<r.threads
            <<",\"construct_on_worker\":"<<(r.construct_on_worker?"true":"false")
            <<",\"warmup_ns\":"<<r.warmup<<",\"maximum_activation_error\":"<<r.maximum_error
            <<",\"all_finite\":"<<(r.finite?"true":"false")<<",\"call_ns\":[";
      for(std::size_t i=0;i<r.calls.size();++i) {if(i) report<<',';report<<r.calls[i];}
      report<<"]}";success=success&&r.finite&&r.maximum_error<=1e-5;
    }
    report<<"]}\n";report.close();if(!report) throw std::runtime_error("diagnosis write failed");
    std::cout<<"Synthetic runtime comparison complete; numerical identity "<<(success?"PASS":"FAIL")<<'\n';
    return success?0:2;
  } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 2;}
}
