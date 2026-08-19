#pragma once
// Modele d'execution — la piece qui decide si un backtest ment.
//
// HYPOTHESE CENTRALE, ET C'EST LA PLUS INFLUENTE DU PROJET.
//   Avec des donnees de haut de carnet seules, une diminution de la taille
//   affichee peut etre une execution (qui fait avancer notre place) ou une
//   annulation (devant ou derriere nous). trade_ratio est la fraction attribuee
//   a ce qui nous fait reellement avancer.
//
//   Une valeur trop genereuse rend N'IMPORTE QUELLE strategie rentable. Le defaut
//   est volontairement pessimiste et DOIT etre recalibre contre les executions
//   reelles avant que tout resultat passif ne soit pris au serieux.

#include "kairos/core/types.hpp"
#include <algorithm>
#include <cmath>
#include <optional>
#include <stdexcept>

namespace kairos::backtest {

using namespace kairos::core;

struct CostModel {
    double commission_bps{0.20};
    double commission_floor{2.00};
    double maker_bps{-1.0};       // < 0 : non defini, on utilise commission_bps

    [[nodiscard]] double commission(double notional, bool is_maker) const noexcept {
        const double bps = (is_maker && maker_bps >= 0.0) ? maker_bps : commission_bps;
        return std::max(commission_floor, std::abs(notional) * bps / 10'000.0);
    }
};

class FillModel {
public:
    explicit FillModel(CostModel cost = {}, double trade_ratio = 0.5)
        : cost_(cost), trade_ratio_(trade_ratio) {
        if (!(trade_ratio >= 0.0 && trade_ratio <= 1.0))
            throw std::invalid_argument("trade_ratio doit etre dans [0, 1]");
    }

    [[nodiscard]] const CostModel& cost() const noexcept { return cost_; }

    [[nodiscard]] std::optional<Fill> process(Order& o, const Quote& q,
                                              const Quote* prev) const {
        if (o.status != OrderStatus::Resting) return std::nullopt;
        if (o.type == OrderType::Market) return fill_market(o, q);
        return try_fill_limit(o, q, prev);
    }

private:
    static constexpr double EPS = 1e-12;

    [[nodiscard]] double size_at_level(const Order& o, const Quote& q) const noexcept {
        return o.side == Side::Buy ? q.bid_size : q.ask_size;
    }
    [[nodiscard]] bool at_touch(const Order& o, const Quote& q) const noexcept {
        const double best = (o.side == Side::Buy) ? q.bid : q.ask;
        return std::abs(best - o.price) < EPS;
    }
    [[nodiscard]] bool crossed(const Order& o, const Quote& q) const noexcept {
        return (o.side == Side::Buy) ? (q.ask <= o.price + EPS)
                                     : (q.bid >= o.price - EPS);
    }

    [[nodiscard]] Fill fill_market(const Order& o, const Quote& q) const {
        const double px = (o.side == Side::Buy) ? q.ask : q.bid;
        Fill f;
        f.order_id = o.id; f.side = o.side; f.qty = o.remaining();
        f.price = px; f.ts_ns = q.ts_wall_ns; f.is_maker = false;
        f.commission = cost_.commission(f.qty * px, false);
        return f;
    }

    [[nodiscard]] Fill make_maker_fill(const Order& o, const Quote& q) const {
        Fill f;
        f.order_id = o.id; f.side = o.side; f.qty = o.remaining();
        f.price = o.price; f.ts_ns = q.ts_wall_ns; f.is_maker = true;
        f.commission = cost_.commission(f.qty * o.price, true);
        return f;
    }

    [[nodiscard]] std::optional<Fill> try_fill_limit(Order& o, const Quote& q,
                                                     const Quote* prev) const {
        // Traversee : le marche vient nous chercher, on est servi a NOTRE prix
        if (crossed(o, q)) return make_maker_fill(o, q);

        if (!at_touch(o, q)) {
            o.joined_queue = false;      // hors du meilleur prix : on perd sa place
            return std::nullopt;
        }
        if (!o.joined_queue) {           // entree au FOND de la file
            o.queue_ahead = size_at_level(o, q);
            o.joined_queue = true;
            return std::nullopt;
        }
        if (prev != nullptr && at_touch(o, *prev)) {
            const double now  = size_at_level(o, q);
            const double before = (o.side == Side::Buy) ? prev->bid_size : prev->ask_size;
            o.queue_ahead -= std::max(0.0, before - now) * trade_ratio_;
        }
        if (o.queue_ahead > 0.0) return std::nullopt;
        return make_maker_fill(o, q);
    }

    CostModel cost_;
    double trade_ratio_;
};

} // namespace kairos::backtest
