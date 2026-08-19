#pragma once
// Metriques de performance, avec correction du multiple testing.
//
// LE PROBLEME
//   Tester deux cents configurations et garder la meilleure donne un Sharpe
//   flatteur meme si aucune n'a le moindre pouvoir predictif : c'est le maximum
//   d'un echantillon de bruit. Le Deflated Sharpe Ratio (Bailey & Lopez de Prado,
//   2014) repond a « quelle est la probabilite que ce Sharpe depasse ce que le
//   hasard produirait, sachant N essais, et compte tenu de l'asymetrie et des
//   queues epaisses des rendements ? »
//
// DEUX CORRECTIONS PAR RAPPORT A L'IMPLEMENTATION PYTHON, MESUREES
//   1. La fonction de repartition passe par erfc. La forme 0.5*(1+erf) renvoyait
//      EXACTEMENT 0.0 des x = -10, la ou la valeur vraie est 7.6e-24. Le PSR
//      d'une mauvaise strategie valait donc 0 au lieu d'une valeur exploitable.
//   2. Le seuil du hasard emploie le quantile complementaire. La forme
//      Phi^-1(1 - 1/N) ECHOUE des N >= 1e16, et derive deja de 7e-4 a N = 1e15.

#include "kairos/math/moments.hpp"
#include "kairos/math/normal.hpp"
#include <cmath>
#include <span>
#include <string>
#include <vector>

namespace kairos::backtest {

namespace km = kairos::math;

[[nodiscard]] inline double sharpe_ratio(std::span<const double> r,
                                         double periods_per_year = 0.0) {
    if (r.size() < 2) return 0.0;
    const auto m = km::compute_moments(r);
    if (km::numerically_flat(m.stddev, r)) return 0.0;
    const double sr = m.mean / m.stddev;
    return periods_per_year > 0.0 ? sr * std::sqrt(periods_per_year) : sr;
}

// PSR : probabilite que le vrai Sharpe depasse sr_benchmark.
// Les deux Sharpe doivent etre exprimes PAR OBSERVATION, jamais annualises.
[[nodiscard]] inline double probabilistic_sharpe_ratio(std::span<const double> r,
                                                       double sr_benchmark = 0.0) {
    const std::size_t T = r.size();
    if (T < 3) return 0.0;
    const auto m = km::compute_moments(r);
    if (km::numerically_flat(m.stddev, r)) return 0.0;

    const double sr = m.mean / m.stddev;
    const double denom_sq = 1.0 - m.skewness * sr
                          + (m.kurtosis - 1.0) / 4.0 * sr * sr;
    if (denom_sq <= 0.0) return 0.0;      // variance estimee non valide

    const double z = (sr - sr_benchmark) * std::sqrt(static_cast<double>(T) - 1.0)
                   / std::sqrt(denom_sq);
    return km::norm_cdf(z);               // erfc : exacte jusqu'a 1e-300
}

// Sharpe maximal ESPERE sous l'hypothese nulle apres n_trials essais.
// Le seuil que le hasard seul atteint : il croit avec le nombre d'essais.
[[nodiscard]] inline double expected_max_sharpe(double n_trials, double sr_variance) {
    if (n_trials < 2.0 || sr_variance <= 0.0) return 0.0;
    const double g = km::EULER_MASCHERONI;
    // Forme complementaire : l'argument reste 1/N, jamais 1 - 1/N.
    const double a = km::norm_quantile_upper(1.0 / n_trials);
    const double b = km::norm_quantile_upper(1.0 / (n_trials * std::exp(1.0)));
    return std::sqrt(sr_variance) * ((1.0 - g) * a + g * b);
}

[[nodiscard]] inline double deflated_sharpe_ratio(std::span<const double> r,
                                                  double n_trials,
                                                  double sr_variance = -1.0) {
    const std::size_t T = r.size();
    if (T < 3) return 0.0;
    if (sr_variance < 0.0) sr_variance = 1.0 / (static_cast<double>(T) - 1.0);
    return probabilistic_sharpe_ratio(r, expected_max_sharpe(n_trials, sr_variance));
}

struct Drawdown { double depth{}; std::size_t peak_idx{}; std::size_t trough_idx{}; };

[[nodiscard]] inline Drawdown max_drawdown(std::span<const double> equity) {
    Drawdown d;
    if (equity.empty()) return d;
    double peak = equity[0];
    std::size_t peak_i = 0;
    for (std::size_t i = 0; i < equity.size(); ++i) {
        if (equity[i] > peak) { peak = equity[i]; peak_i = i; }
        const double dd = (peak != 0.0) ? (peak - equity[i]) / std::abs(peak) : 0.0;
        if (dd > d.depth) { d.depth = dd; d.peak_idx = peak_i; d.trough_idx = i; }
    }
    return d;
}

[[nodiscard]] inline double sortino_ratio(std::span<const double> r,
                                          double periods_per_year = 0.0) {
    if (r.size() < 2) return 0.0;
    double sum = 0.0;
    for (double x : r) sum += x;
    const double mean = sum / static_cast<double>(r.size());

    double dsum = 0.0; std::size_t n_down = 0;
    for (double x : r) if (x < 0.0) { dsum += x * x; ++n_down; }
    if (n_down == 0) return mean > 0.0 ? std::numeric_limits<double>::infinity() : 0.0;

    const double dd = std::sqrt(dsum / static_cast<double>(n_down));
    if (km::numerically_flat(dd, r)) return 0.0;
    const double s = mean / dd;
    return periods_per_year > 0.0 ? s * std::sqrt(periods_per_year) : s;
}

struct PerformanceReport {
    std::size_t n_observations{};
    double total_return{}, sharpe{}, sharpe_annualised{}, sortino{};
    double max_drawdown{}, psr{}, dsr{};
    double n_trials{}, skew{}, kurtosis{};
    std::string verdict, warning;
};

[[nodiscard]] inline PerformanceReport make_report(std::span<const double> returns,
                                                   std::span<const double> equity,
                                                   double n_trials = 1.0,
                                                   double periods_per_year = 252.0) {
    PerformanceReport p;
    p.n_observations = returns.size();
    p.n_trials = n_trials;

    const auto m = km::compute_moments(returns);
    p.skew = m.skewness;
    p.kurtosis = m.kurtosis;
    p.sharpe = sharpe_ratio(returns);
    p.sharpe_annualised = sharpe_ratio(returns, periods_per_year);
    p.sortino = sortino_ratio(returns, periods_per_year);
    p.max_drawdown = max_drawdown(equity).depth;
    p.psr = probabilistic_sharpe_ratio(returns);
    p.dsr = deflated_sharpe_ratio(returns, n_trials);
    p.total_return = (!equity.empty() && equity.front() != 0.0)
        ? (equity.back() - equity.front()) / std::abs(equity.front()) : 0.0;

    p.verdict = p.dsr > 0.95 ? "RETENIR"
              : p.dsr > 0.50 ? "INSUFFISANT"
                             : "INDISCERNABLE DU HASARD";

    // Racine-temps suppose des rendements independants. A l'echelle du tick ils
    // sont fortement autocorreles : un Sharpe annualise a quatre chiffres est un
    // artefact d'echelle, pas une performance.
    if (periods_per_year > 1'000'000.0)
        p.warning = "facteur d'annualisation extreme : lire le Sharpe par "
                    "observation et le DSR, pas l'annualise";
    return p;
}

} // namespace kairos::backtest
