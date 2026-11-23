// SPDX-License-Identifier: AGPL-3.0-only
// Standalone research adapter for the pinned AGPL-3.0 Soundshed detector.
// Not linked into, or installed with, the M3 production plugin.
// Compilation and execution are permitted on GitHub Actions only.
#include "dsp/PolyNoteDetector.h"
#include "dsp/PolyNoteModel.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    try {
        const char* guard = std::getenv("GITHUB_ACTIONS");
        if (!guard || std::string(guard) != "true")
            throw std::runtime_error("Detector execution requires GitHub Actions");
        if (argc != 7)
            throw std::runtime_error("Usage: replay input.f32 sample_rate samples block events.tsv timing.json");
        const int rate = std::stoi(argv[2]);
        const std::size_t count = std::stoull(argv[3]);
        const int block = std::stoi(argv[4]);
        if (rate != 96000 || !count || count > 20000000 || block < 1 || block > 4096)
            throw std::runtime_error("Invalid frozen input clock or block");
        std::ifstream input(argv[1], std::ios::binary | std::ios::ate);
        if (!input || input.tellg() != static_cast<std::streamoff>(count * sizeof(float)))
            throw std::runtime_error("Raw float32 input length differs");
        std::vector<float> audio(count);
        input.seekg(0);
        input.read(reinterpret_cast<char*>(audio.data()), count * sizeof(float));
        if (!input || !std::all_of(audio.begin(), audio.end(), [](float x) { return std::isfinite(x); }))
            throw std::runtime_error("Invalid input samples");
        guitarfx::PolyNoteDetector detector;
        detector.Prepare(rate, guitarfx::poly_note_model::Model());
        detector.SetThresholdDb(-50.0);
        detector.SetLowestNote(35);
        detector.SetFollowPitch(false);
        std::ofstream events(argv[5]);
        events << "sample\tkind\tnote\tvelocity\tsequence\n" << std::setprecision(9);
        std::vector<long long> timings;
        timings.reserve((count + block - 1) / block);
        std::size_t sequence = 0, overruns = 0;
        long long total = 0;
        std::array<guitarfx::PolyNoteDetector::Event, 4096> buffer;
        for (std::size_t start = 0; start < count; start += block) {
            const int size = static_cast<int>(std::min<std::size_t>(block, count - start));
            std::size_t used = 0;
            bool overflow = false;
            const auto before = std::chrono::steady_clock::now();
            detector.Process(audio.data() + start, size, [&](const auto& event) {
                if (used < buffer.size()) buffer[used++] = event;
                else overflow = true;
            });
            const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now() - before).count();
            if (overflow) throw std::runtime_error("Event buffer capacity exceeded");
            timings.push_back(elapsed);
            total += elapsed;
            overruns += elapsed * static_cast<long long>(rate) > static_cast<long long>(size) * 1000000000LL;
            for (std::size_t i = 0; i < used; ++i) {
                const auto& e = buffer[i];
                using Type = guitarfx::PolyNoteDetector::Event::Type;
                if (e.type == Type::Bend || e.sampleOffset < 0 || e.sampleOffset >= size)
                    throw std::runtime_error("Unexpected event type or callback offset");
                events << start + e.sampleOffset << '\t' << (e.type == Type::Start ? "on" : "off")
                       << '\t' << e.note << '\t' << e.velocity << '\t' << sequence++ << '\n';
            }
        }
        events.close();
        if (!events) throw std::runtime_error("Event write failed");
        std::sort(timings.begin(), timings.end());
        const auto quantile = [&](double q) {
            return timings[static_cast<std::size_t>(std::ceil(q * timings.size())) - 1];
        };
        std::ofstream stats(argv[6]);
        stats << "{\"sample_rate\":" << rate << ",\"samples\":" << count
              << ",\"block\":" << block << ",\"callbacks\":" << timings.size()
              << ",\"detector_frames\":" << detector.FrameCount()
              << ",\"hop_samples\":" << detector.HopSamples()
              << ",\"events\":" << sequence << ",\"processing_ns\":" << total
              << ",\"p50_ns\":" << quantile(.5) << ",\"p95_ns\":" << quantile(.95)
              << ",\"p99_ns\":" << quantile(.99) << ",\"max_ns\":" << timings.back()
              << ",\"callback_deadline_overruns\":" << overruns
              << ",\"m3_p99_limit_ns\":166666,\"m3_max_limit_ns\":333333"
              << ",\"m3_timing_limits_pass\":"
              << ((quantile(.99) <= 166666 && timings.back() <= 333333 && !overruns) ? "true" : "false")
              << ",\"allocation_check\":\"not measured\""
              << ",\"scope\":\"Detector Process plus bounded preallocated sink; I/O, preparation and scoring excluded. Native runner, not host timing.\"}\n";
        stats.close();
        if (!stats) throw std::runtime_error("Timing write failed");
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
