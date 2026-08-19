#pragma once
// Moteur de backtest evenementiel, deterministe.
//
// TROIS GARANTIES
//   1. AUCUN LOOK-AHEAD — la strategie ne voit qu'une quote a la fois.
//   2. LATENCE INCOMPRESSIBLE — un ordre decide en t arrive en t + latence, et ne
//      peut donc PAS s'executer contre la quote qui l'a declenche. C'est l'erreur
//      la plus rentable des backtests naifs.
//   3. DETERMINISME — memes entrees, meme sortie, toujours.
//
// Une annulation atteint aussi bien un ordre EN VOL qu'un ordre deja pose : ne
// traiter que le carnet laisserait passer tout ordre emis dans la derniere
// fenetre de latence, qui se poserait ensuite alors qu'on le croit annule.

#include "kairos/backtest/fills.hpp"
#include "kairos/core/portfolio.hpp"
#include <algorithm>
#include <functional>
#include <span>
#include <stdexcept>
#include <unordered_map>
#include <vector>

namespace kairos::backtest {

struct Action {
    enum class Kind { Submit, Cancel } kind{Kind::Submit};
    core::Order order{};
    std::int64_t client_id{};
};

struct BacktestResult {
    std::vector<std::pair<std::int64_t, double>> equity_curve;
    core::Portfolio portfolio;
    std::size_t n_quotes{}, n_orders{}, n_fills{}, n_cancelled{};

    [[nodiscard]] std::vector<double> returns() const {
        std::vector<double> out;
        out.reserve(equity_curve.size());
        for (std::size_t i = 1; i < equity_curve.size(); ++i) {
            const double a = equity_curve[i - 1].second, b = equity_curve[i].second;
            out.push_back(a != 0.0 ? (b - a) / std::abs(a) : 0.0);
        }
        return out;
    }
};

class Strategy {
public:
    virtual ~Strategy() = default;
    virtual std::vector<Action> on_quote(const core::Quote&, const core::Portfolio&) = 0;
    virtual void on_fill(const core::Fill&) {}
};

class Engine {
public:
    Engine(Strategy& s, CostModel cost = {}, std::int64_t latency_ns = 50'000'000,
           double trade_ratio = 0.5, double initial_cash = 0.0)
        : strat_(s), fills_(cost, trade_ratio), latency_(latency_ns), cash0_(initial_cash) {
        if (latency_ns <= 0)
            throw std::invalid_argument(
                "latency_ns doit etre > 0 : une latence nulle autorise la strategie "
                "a s'executer contre la quote qui l'a declenchee, ce qui est impossible");
    }

    [[nodiscard]] BacktestResult run(std::span<const core::Quote> quotes) {
        using namespace core;
        BacktestResult res;
        res.portfolio.set_cash(cash0_);
        res.equity_curve.reserve(quotes.size());

        std::vector<Order> pending;
        std::unordered_map<std::int64_t, Order> resting;
        std::unordered_map<std::int64_t, std::int64_t> client_to_id;
        std::vector<std::pair<std::int64_t, std::int64_t>> pending_cancels;
        std::int64_t next_id = 1;
        const Quote* prev = nullptr;

        for (const auto& q : quotes) {
            const std::int64_t now = q.ts_wall_ns;
            ++res.n_quotes;

            // 1. Annulations arrivees — carnet ET ordres en vol
            std::erase_if(pending_cancels, [&](const auto& pc) {
                if (pc.first > now) return false;
                const auto it = client_to_id.find(pc.second);
                if (it != client_to_id.end()) {
                    const auto rit = resting.find(it->second);
                    if (rit != resting.end() && rit->second.is_active()) {
                        resting.erase(rit); ++res.n_cancelled; return true;
                    }
                    const auto pit = std::find_if(pending.begin(), pending.end(),
                        [&](const Order& o){ return o.client_id == pc.second; });
                    if (pit != pending.end()) {
                        pending.erase(pit); ++res.n_cancelled;
                    }
                }
                return true;
            });

            // 2. Ordres arrives
            std::erase_if(pending, [&](Order& o) {
                if (o.ts_arrive_ns > now) return false;
                o.status = OrderStatus::Resting;
                resting.emplace(o.id, o);
                return true;
            });

            // 3. Confrontation au carnet
            for (auto it = resting.begin(); it != resting.end(); ) {
                auto fill = fills_.process(it->second, q, prev);
                if (!fill) { ++it; continue; }
                res.portfolio.apply(*fill);
                ++res.n_fills;
                strat_.on_fill(*fill);
                it = resting.erase(it);
            }

            // 4. Decision — APRES les executions, sur l'etat courant
            for (auto& a : strat_.on_quote(q, res.portfolio)) {
                if (a.kind == Action::Kind::Submit) {
                    Order o = a.order;
                    o.id = next_id++;
                    o.ts_created_ns = now;
                    o.ts_arrive_ns = now + latency_;   // la latence, toujours
                    o.status = OrderStatus::Pending;
                    client_to_id[o.client_id] = o.id;
                    pending.push_back(o);
                    ++res.n_orders;
                } else {
                    pending_cancels.emplace_back(now + latency_, a.client_id);
                }
            }

            // 5. Marquage au mid
            res.equity_curve.emplace_back(now, res.portfolio.equity(q.mid()));
            prev = &q;
        }
        return res;
    }

private:
    Strategy& strat_;
    FillModel fills_;
    std::int64_t latency_;
    double cash0_;
};

} // namespace kairos::backtest
