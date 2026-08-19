#pragma once
// Cash and carry — long spot, short perpetuel, delta neutre.
//
// LE PIEGE QUE CE MODULE CHIFFRE
//   Les deux jambes ne vivent PAS sur le meme compte : le spot au comptant, le
//   perpetuel sur le compte derives — separation renforcee sous MiFID.
//
//   En MARGE ISOLEE, la jambe perpetuelle peut donc etre liquidee alors qu'on
//   detient une plus-value latente EXACTEMENT EGALE sur le spot, simplement parce
//   qu'elle n'est pas mobilisable comme collateral. On est liquide sur une
//   position dont le risque net etait nul : ce n'est pas un risque de marche,
//   c'est un risque de PLOMBERIE.

#include <cmath>
#include <limits>
#include <span>
#include <stdexcept>
#include <vector>

namespace kairos::carry {

struct FundingEvent {
    std::int64_t ts_ns{};
    double rate_bps{};      // positif : les longs paient les shorts
    double mark_price{};

    [[nodiscard]] double payment(double position) const noexcept {
        return -position * mark_price * rate_bps / 10'000.0;
    }
};

struct Config {
    double spot_fee_bps{25.0};              // Kraken UE, tier de base
    double perp_fee_bps{2.0};
    double max_leverage{2.0};               // plafond retail UE
    double maintenance_margin_rate{0.005};
    bool   isolated_margin{true};           // LE parametre decisif
    double slippage_bps{2.0};

    void validate() const {
        if (max_leverage <= 0.0)
            throw std::invalid_argument("max_leverage doit etre strictement positif");
        if (!(maintenance_margin_rate > 0.0 && maintenance_margin_rate < 1.0))
            throw std::invalid_argument("maintenance_margin_rate hors de ]0, 1[");
    }
};

struct Result {
    double entry_price{}, exit_price{}, notional{}, margin_posted{}, capital{};
    double funding_bps{}, fees_bps{}, net_position_bps{}, net_capital_bps{};
    bool   liquidated{false};
    std::int64_t ts_liquidation{};
    double liquidation_price{};
    double min_margin_ratio{std::numeric_limits<double>::infinity()};
    double days_held{};
    std::size_t n_funding{}, n_funding_negative{};

    [[nodiscard]] double net_annualised() const noexcept {
        return days_held > 0.0 ? net_capital_bps / 10'000.0 * 365.0 / days_held : 0.0;
    }
};

class Simulator {
public:
    explicit Simulator(Config c = {}) : cfg_(c) { cfg_.validate(); }

    // Prix au-dela duquel la jambe short est liquidee, en marge isolee.
    //
    //   marge restante = M + X(p0 - p),  exigence = mmr . X . p
    //   liquidation quand  M/X + p0 - p <= mmr . p
    //   soit               p >= p0 (1/L + 1) / (1 + mmr)
    //
    // En marge croisee la plus-value du spot compense : le seuil part a l'infini.
    [[nodiscard]] double liquidation_price(double entry) const noexcept {
        if (!cfg_.isolated_margin) return std::numeric_limits<double>::infinity();
        return entry * (1.0 / cfg_.max_leverage + 1.0) / (1.0 + cfg_.maintenance_margin_rate);
    }

    [[nodiscard]] Result run(std::span<const std::pair<std::int64_t, double>> prices,
                             std::span<const FundingEvent> funding,
                             double capital = 10'000.0) const {
        if (prices.empty()) throw std::invalid_argument("aucun prix fourni");

        const auto [ts0, p0] = prices.front();

        // capital = spot (1) + marge sur le short (1/L)
        const double capital_per_unit = 1.0 + 1.0 / cfg_.max_leverage;
        const double notional = capital / capital_per_unit;
        const double qty      = notional / p0;
        const double margin   = notional / cfg_.max_leverage;

        const double fee_in  = cfg_.spot_fee_bps + cfg_.perp_fee_bps + cfg_.slippage_bps / 2.0;
        const double fee_out = fee_in;

        Result r;
        r.entry_price = p0; r.exit_price = p0; r.notional = notional;
        r.margin_posted = margin; r.capital = capital;
        r.liquidation_price = liquidation_price(p0);

        double funding_cum = 0.0;
        std::size_t fi = 0;

        for (const auto& [ts, p] : prices) {
            while (fi < funding.size() && funding[fi].ts_ns <= ts) {
                funding_cum += funding[fi].payment(-qty);   // position short
                ++r.n_funding;
                if (funding[fi].rate_bps < 0.0) ++r.n_funding_negative;
                ++fi;
            }

            double equity = margin + qty * (p0 - p) + funding_cum;
            if (!cfg_.isolated_margin) equity += qty * (p - p0);   // marge croisee

            const double requirement = cfg_.maintenance_margin_rate * qty * p;
            const double ratio = (qty * p > 0.0) ? equity / (qty * p) : 0.0;
            r.min_margin_ratio = std::min(r.min_margin_ratio, ratio);

            if (equity <= requirement) {
                r.liquidated = true; r.ts_liquidation = ts; r.exit_price = p;
                break;
            }
            r.exit_price = p;
        }

        const std::int64_t ts_end = r.liquidated ? r.ts_liquidation : prices.back().first;
        r.days_held  = static_cast<double>(ts_end - ts0) / 1e9 / 86'400.0;
        r.funding_bps = funding_cum / notional * 10'000.0;
        r.fees_bps    = fee_in + (r.liquidated ? 0.0 : fee_out);

        if (r.liquidated) {
            // La marge du perpetuel est perdue. Le spot subsiste avec sa
            // plus-value, mais la couverture a disparu : la position n'est plus neutre.
            r.net_position_bps = r.funding_bps - margin / notional * 10'000.0 - r.fees_bps;
        } else {
            r.net_position_bps = r.funding_bps - r.fees_bps;
        }
        r.net_capital_bps = r.net_position_bps * (notional / capital);
        return r;
    }

private:
    Config cfg_;
};

} // namespace kairos::carry
