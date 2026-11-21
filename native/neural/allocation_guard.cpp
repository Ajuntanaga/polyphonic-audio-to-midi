#include "allocation_guard.hpp"
#include <cstdlib>
#include <new>
namespace {
thread_local bool enabled=false;
thread_local m3::neural::Allocations counts{};
void allocate() noexcept {if(enabled) ++counts.allocations;}
void deallocate(void* p) noexcept {if(enabled && p) ++counts.deallocations;}
}
namespace m3::neural {
void begin_callback_allocations() noexcept {counts={};enabled=true;}
Allocations end_callback_allocations() noexcept {enabled=false;return counts;}
}
extern "C" {
void* __real_malloc(std::size_t);
void* __real_calloc(std::size_t,std::size_t);
void* __real_realloc(void*,std::size_t);
void* __real_aligned_alloc(std::size_t,std::size_t);
int __real_posix_memalign(void**,std::size_t,std::size_t);
void __real_free(void*);
void* __wrap_malloc(std::size_t n) {allocate();return __real_malloc(n);}
void* __wrap_calloc(std::size_t n,std::size_t s) {allocate();return __real_calloc(n,s);}
void* __wrap_realloc(void* p,std::size_t n) {allocate();deallocate(p);return __real_realloc(p,n);}
void* __wrap_aligned_alloc(std::size_t a,std::size_t n) {allocate();return __real_aligned_alloc(a,n);}
int __wrap_posix_memalign(void** p,std::size_t a,std::size_t n) {allocate();return __real_posix_memalign(p,a,n);}
void __wrap_free(void* p) {deallocate(p);__real_free(p);}
}
// Global new replacements count C++ calls explicitly; real malloc avoids double counting.
void* operator new(std::size_t n) {allocate();if(auto* p=__real_malloc(n?n:1))return p;throw std::bad_alloc();}
void* operator new[](std::size_t n) {return ::operator new(n);}
void operator delete(void* p) noexcept {deallocate(p);__real_free(p);}
void operator delete[](void* p) noexcept {::operator delete(p);}
void operator delete(void* p,std::size_t) noexcept {::operator delete(p);}
void operator delete[](void* p,std::size_t) noexcept {::operator delete(p);}
void* operator new(std::size_t n,std::align_val_t a) {
 allocate();void* p=nullptr;if(__real_posix_memalign(&p,static_cast<std::size_t>(a),n?n:1)==0)return p;
 throw std::bad_alloc();
}
void* operator new[](std::size_t n,std::align_val_t a) {return ::operator new(n,a);}
void operator delete(void* p,std::align_val_t) noexcept {::operator delete(p);}
void operator delete[](void* p,std::align_val_t) noexcept {::operator delete(p);}
void operator delete(void* p,std::size_t,std::align_val_t) noexcept {::operator delete(p);}
void operator delete[](void* p,std::size_t,std::align_val_t) noexcept {::operator delete(p);}
void* operator new(std::size_t n,const std::nothrow_t&) noexcept {try{return ::operator new(n);}catch(...){return nullptr;}}
void* operator new[](std::size_t n,const std::nothrow_t& t) noexcept {return ::operator new(n,t);}
void operator delete(void* p,const std::nothrow_t&) noexcept {::operator delete(p);}
void operator delete[](void* p,const std::nothrow_t&) noexcept {::operator delete(p);}
void* operator new(std::size_t n,std::align_val_t a,const std::nothrow_t&) noexcept {try{return ::operator new(n,a);}catch(...){return nullptr;}}
void* operator new[](std::size_t n,std::align_val_t a,const std::nothrow_t& t) noexcept {return ::operator new(n,a,t);}
void operator delete(void* p,std::align_val_t,const std::nothrow_t&) noexcept {::operator delete(p);}
void operator delete[](void* p,std::align_val_t,const std::nothrow_t&) noexcept {::operator delete(p);}
