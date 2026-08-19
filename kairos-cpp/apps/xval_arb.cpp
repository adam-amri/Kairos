// Pendant C++ de scripts/xval_arb.py. Memes entrees, memes grandeurs.
#include "kairos/arb/detector.hpp"
#include <cstdio>
using namespace kairos::arb;

int main() {
    const struct { const char *b, *q; double bid, ask; } P[] = {
        {"EUR","USD",1.08000,1.08004}, {"USD","JPY",157.000,157.006},
        {"GBP","USD",1.27150,1.27160}, {"EUR","GBP",0.84930,0.84937},
        {"USD","CHF",0.88120,0.88127}, {"AUD","USD",0.66410,0.66417},
        {"EUR","JPY",169.562,169.572}, {"GBP","JPY",199.640,199.652}};
    Detector d;
    for (const auto& p : P) d.add_pair({p.b, p.q, p.bid, p.ask});

    std::printf("n_devises %zu\n", d.n_currencies());
    std::printf("n_paires %zu\n", d.n_pairs());
    for (int k = 3; k <= 5; ++k)
        std::printf("cycles_%d %zu\n", k, d.enumerate_cycles(k).size());

    const CostModel c{0.20, 2.00, 0.0};
    const struct { DeviationBasis b; const char* n; } bases[] = {
        {DeviationBasis::Executable, "executable"}, {DeviationBasis::Mid, "mid"}};
    for (const auto& bs : bases)
        for (double notional : {10'000.0, 100'000.0}) {
            const auto o = d.scan(c, notional, 3, 5, false, bs.b);
            char tag[64];
            std::snprintf(tag, sizeof tag, "%s_%.0f", bs.n, notional);
            std::printf("%s_n %zu\n", tag, o.size());
            std::printf("%s_best_gross %.17e\n", tag, o.front().gross_bps);
            std::printf("%s_best_cost %.17e\n", tag, o.front().cost_bps);
            std::printf("%s_best_net %.17e\n", tag, o.front().net_bps);
            double s = 0; for (const auto& x : o) s += x.net_bps;
            std::printf("%s_sum_net %.17e\n", tag, s);
            std::printf("%s_worst_net %.17e\n", tag, o.back().net_bps);
        }
    std::printf("gbpusd_rate %.17e\n", d.resolve("GBP","USD")->rate);
    std::printf("usdgbp_rate %.17e\n", d.resolve("USD","GBP")->rate);
    return 0;
}
