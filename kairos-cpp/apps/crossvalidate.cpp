// Sortie machine pour confrontation avec l'implementation Python.
// Toute divergence au-dela de la tolerance annoncee est un bug dans l'une des deux.
#include "kairos/backtest/metrics.hpp"
#include "kairos/carry/simulator.hpp"
#include "kairos/core/portfolio.hpp"
#include <cstdio>
#include <vector>

using namespace kairos;
using namespace kairos::backtest;

int main() {
    // Serie deterministe : reproductible a l'identique des deux cotes
    std::vector<double> r;
    r.reserve(2000);
    for (int i = 0; i < 2000; ++i)
        r.push_back(0.0004 * std::sin(i * 0.37) + 0.00002 * i - 0.00001 * (i % 7));

    std::vector<double> eq{100.0};
    for (double x : r) eq.push_back(eq.back() * (1.0 + x));

    std::printf("sharpe %.17e\n", sharpe_ratio(r));
    std::printf("sharpe_ann %.17e\n", sharpe_ratio(r, 252.0));
    std::printf("sortino %.17e\n", sortino_ratio(r, 252.0));
    std::printf("maxdd %.17e\n", max_drawdown(eq).depth);
    std::printf("psr %.17e\n", probabilistic_sharpe_ratio(r));
    for (double n : {2.0, 100.0, 1e4, 1e8, 1e15})
        std::printf("ems_%.0e %.17e\n", n, expected_max_sharpe(n, 0.01));
    for (double n : {2.0, 40.0, 1000.0, 1e6})
        std::printf("dsr_%.0e %.17e\n", n, deflated_sharpe_ratio(r, n));

    const auto m = math::compute_moments(r);
    std::printf("mean %.17e\nvar %.17e\nskew %.17e\nkurt %.17e\n",
                m.mean, m.variance, m.skewness, m.kurtosis);

    // Portefeuille : sequence identique des deux cotes
    core::Portfolio pf;
    const struct { core::Side s; double q, p; } seq[] = {
        {core::Side::Buy, 100, 10.0}, {core::Side::Buy, 100, 12.0},
        {core::Side::Sell, 40, 15.0}, {core::Side::Sell, 300, 9.0},
        {core::Side::Buy, 50, 8.0}};
    for (const auto& f : seq) {
        core::Fill fl; fl.side = f.s; fl.qty = f.q; fl.price = f.p; fl.is_maker = true;
        pf.apply(fl);
    }
    std::printf("pf_position %.17e\npf_avg %.17e\npf_realised %.17e\npf_cash %.17e\n",
                pf.position(), pf.avg_price(), pf.realised_pnl(), pf.cash());

    // Cash and carry
    carry::Simulator sim{{25.0, 2.0, 2.0, 0.005, true, 2.0}};
    std::printf("liq_price %.17e\n", sim.liquidation_price(100.0));
    std::vector<std::pair<std::int64_t, double>> px;
    for (int i = 0; i < 90 * 24; ++i) px.emplace_back(std::int64_t(i) * 3'600'000'000'000LL, 100.0);
    std::vector<carry::FundingEvent> fd;
    for (int i = 0; i < 270; ++i) fd.push_back({std::int64_t(i + 1) * 28'800'000'000'000LL, 1.0, 100.0});
    const auto cr = sim.run(px, fd, 10'000.0);
    std::printf("carry_funding %.17e\ncarry_fees %.17e\ncarry_net_cap %.17e\ncarry_ann %.17e\n",
                cr.funding_bps, cr.fees_bps, cr.net_capital_bps, cr.net_annualised());
    return 0;
}
