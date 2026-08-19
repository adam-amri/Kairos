#pragma once
// Comptabilite des positions.
//
// Deux cas que les implementations naives traitent mal, et qui faussent
// silencieusement tout le P&L realise :
//
//   REDUCTION PARTIELLE — on constate le resultat, mais le prix moyen d'entree
//   ne bouge PAS. Le recalculer a chaque execution est l'erreur classique.
//
//   INVERSION — passer de +100 a -50 par une vente de 150, c'est solder +100
//   (resultat realise sur 100, jamais sur 150) puis ouvrir -50 au prix de
//   l'execution.

#include "kairos/core/types.hpp"
#include <cmath>
#include <vector>

namespace kairos::core {

class Portfolio {
public:
    void apply(const Fill& f) {
        const double q = f.signed_qty();
        cash_ -= q * f.price;
        cash_ -= f.commission;
        total_commission_ += f.commission;
        ++n_fills_;

        const double old_pos = position_;
        const double old_avg = avg_price_;
        const double new_pos = old_pos + q;

        if (old_pos == 0.0 || (old_pos > 0.0) == (q > 0.0)) {
            // Ouverture ou renforcement
            avg_price_ = (new_pos != 0.0)
                ? (std::abs(old_pos) * old_avg + std::abs(q) * f.price) / std::abs(new_pos)
                : 0.0;
        } else if (std::abs(q) <= std::abs(old_pos)) {
            // Reduction : on realise, la moyenne reste inchangee
            const double dir = (old_pos > 0.0) ? 1.0 : -1.0;
            realised_pnl_ += std::abs(q) * (f.price - old_avg) * dir;
            if (new_pos == 0.0) avg_price_ = 0.0;
        } else {
            // Inversion : solder l'ancienne, ouvrir la nouvelle
            const double dir = (old_pos > 0.0) ? 1.0 : -1.0;
            realised_pnl_ += std::abs(old_pos) * (f.price - old_avg) * dir;
            avg_price_ = f.price;
        }
        position_ = new_pos;
    }

    [[nodiscard]] double unrealised_pnl(double mark) const noexcept {
        return position_ == 0.0 ? 0.0 : position_ * (mark - avg_price_);
    }
    [[nodiscard]] double equity(double mark) const noexcept { return cash_ + position_ * mark; }
    [[nodiscard]] double total_pnl(double mark) const noexcept {
        return realised_pnl_ + unrealised_pnl(mark);
    }

    [[nodiscard]] double cash() const noexcept { return cash_; }
    [[nodiscard]] double position() const noexcept { return position_; }
    [[nodiscard]] double avg_price() const noexcept { return avg_price_; }
    [[nodiscard]] double realised_pnl() const noexcept { return realised_pnl_; }
    [[nodiscard]] double total_commission() const noexcept { return total_commission_; }
    [[nodiscard]] std::size_t n_fills() const noexcept { return n_fills_; }

    void set_cash(double c) noexcept { cash_ = c; }

private:
    double cash_{}, position_{}, avg_price_{};
    double realised_pnl_{}, total_commission_{};
    std::size_t n_fills_{};
};

} // namespace kairos::core
