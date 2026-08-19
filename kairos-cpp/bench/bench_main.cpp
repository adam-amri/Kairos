// Benchmark : ou le C++ gagne reellement sa place.
#include "kairos/backtest/engine.hpp"
#include "kairos/backtest/metrics.hpp"
#include <chrono>
#include <cstdio>
#include <random>
#include <vector>

using namespace kairos;
using namespace kairos::core;
using namespace kairos::backtest;

class PassiveQuoter final : public Strategy {
public:
    explicit PassiveQuoter(double edge_bps = 0.05, double qty = 25'000)
        : edge_(edge_bps), qty_(qty) {}

    std::vector<Action> on_quote(const Quote& q, const Portfolio&) override {
        std::vector<Action> acts;
        const double mid = q.mid(), d = mid * edge_ / 10'000.0;
        for (auto side : {Side::Buy, Side::Sell}) {
            const double target = (side == Side::Buy) ? mid - d : mid + d;
            auto& live = (side == Side::Buy) ? live_buy_ : live_sell_;
            if (live.first != 0) {
                if (std::abs(live.second - target) / mid * 10'000.0 < 0.5) continue;
                Action c; c.kind = Action::Kind::Cancel; c.client_id = live.first;
                acts.push_back(c);
            }
            Action a; a.kind = Action::Kind::Submit;
            a.order.client_id = ++next_cid_;
            a.order.side = side; a.order.qty = qty_;
            a.order.type = OrderType::Limit; a.order.price = target;
            acts.push_back(a);
            live = {next_cid_, target};
        }
        return acts;
    }
    void on_fill(const Fill& f) override {
        ((f.side == Side::Buy) ? live_buy_ : live_sell_) = {0, 0.0};
    }
private:
    double edge_, qty_;
    std::int64_t next_cid_{};
    std::pair<std::int64_t, double> live_buy_{}, live_sell_{};
};

int main(int argc, char** argv) {
    const std::size_t N = (argc > 1) ? std::stoul(argv[1]) : 1'000'000;

    std::vector<Quote> quotes;
    quotes.reserve(N);
    std::mt19937_64 rng(42);
    std::normal_distribution<double> g(0.0, 0.00003);
    double mid = 1.08;
    for (std::size_t i = 0; i < N; ++i) {
        mid *= 1.0 + g(rng);
        const double half = mid * 0.28 / 2 / 10'000.0;
        Quote q;
        q.ts_venue_ns = q.ts_wall_ns = q.ts_mono_ns = std::int64_t(i) * 50'000'000LL;
        q.bid = mid - half; q.ask = mid + half;
        q.bid_size = q.ask_size = 1'000'000;
        quotes.push_back(q);
    }

    PassiveQuoter strat;
    Engine eng(strat, CostModel{0.20, 0.0, -1.0}, 20'000'000LL, 0.5, 100'000.0);

    const auto t0 = std::chrono::steady_clock::now();
    const auto res = eng.run(quotes);
    const auto t1 = std::chrono::steady_clock::now();

    const double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
    const auto rets = res.returns();
    std::vector<double> eq;
    eq.reserve(res.equity_curve.size());
    for (const auto& [t, v] : res.equity_curve) eq.push_back(v);

    const auto t2 = std::chrono::steady_clock::now();
    const auto rep = make_report(rets, eq, 40.0, 6.3e8);
    const auto t3 = std::chrono::steady_clock::now();
    const double ms_metrics = std::chrono::duration<double, std::milli>(t3 - t2).count();

    std::printf("quotes            : %zu\n", res.n_quotes);
    std::printf("ordres            : %zu\n", res.n_orders);
    std::printf("executions        : %zu\n", res.n_fills);
    std::printf("annulations       : %zu\n", res.n_cancelled);
    std::printf("moteur            : %.1f ms  (%.2f M quotes/s)\n", ms, N / ms / 1000.0);
    std::printf("metriques         : %.2f ms\n", ms_metrics);
    std::printf("rendement total   : %+.4f %%\n", rep.total_return * 100);
    std::printf("Sharpe /obs       : %+.6f\n", rep.sharpe);
    std::printf("DSR (40 essais)   : %.6f\n", rep.dsr);
    std::printf("verdict           : %s\n", rep.verdict.c_str());
    return 0;
}
