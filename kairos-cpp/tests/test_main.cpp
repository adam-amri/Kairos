// Suite de tests C++ — valeurs de reference generees par mpmath a 300 chiffres.
#include "kairos/backtest/engine.hpp"
#include "kairos/backtest/metrics.hpp"
#include "kairos/carry/simulator.hpp"
#include "kairos/core/portfolio.hpp"
#include "kairos/math/normal.hpp"
#include "reference_values.hpp"

#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

static int g_pass = 0, g_fail = 0;

static void check(bool ok, const std::string& name, const std::string& detail = "") {
    if (ok) { ++g_pass; }
    else { ++g_fail; std::printf("  ECHEC  %s%s%s\n", name.c_str(),
                                 detail.empty() ? "" : " — ", detail.c_str()); }
}
// Tolerance MIXTE : relative, avec un plancher absolu.
// Une comparaison purement relative est inutilisable quand la valeur attendue
// vaut zero : l'erreur relative y explose sur un resultat pourtant exact.
static void check_close(double got, double want, double rel_tol,
                        const std::string& name, double abs_tol = 1e-300) {
    const double diff = std::abs(got - want);
    const bool ok = diff <= abs_tol || diff <= rel_tol * std::abs(want);
    check(ok, name, ok ? "" : "obtenu " + std::to_string(got) +
                              " attendu " + std::to_string(want) +
                              " ecart " + std::to_string(diff));
}

using namespace kairos;
using namespace kairos::core;
using namespace kairos::backtest;

// ------------------------------------------------------------------ maths
static void test_normal() {
    double worst_cdf = 0.0;
    for (const auto& c : ref::CDF) {
        const double v = math::norm_cdf(c.x);
        const double rel = std::abs(v - c.expected) / c.expected;
        worst_cdf = std::max(worst_cdf, rel);
        check(rel < 1e-14, "cdf(" + std::to_string(c.x) + ")");
    }
    std::printf("  cdf      : erreur relative maximale %.3e (sur %zu cas)\n",
                worst_cdf, std::size(ref::CDF));

    double worst_q = 0.0;
    for (const auto& q : ref::QUANTILE) {
        const double v = math::norm_quantile(q.p);
        const double denom = std::abs(q.expected) > 1e-30 ? std::abs(q.expected) : 1.0;
        const double rel = std::abs(v - q.expected) / denom;
        worst_q = std::max(worst_q, rel);
        check(rel < 1e-14, "quantile(" + std::to_string(q.p) + ")");
    }
    std::printf("  quantile : erreur relative maximale %.3e (sur %zu cas)\n",
                worst_q, std::size(ref::QUANTILE));

    // Aller-retour sur toute la plage representable
    double worst_rt = 0.0, worst_p = 0.0;
    for (double p = 1e-300; p < 1.0; p *= 1.7) {
        const double rel = std::abs(math::norm_cdf(math::norm_quantile(p)) - p) / p;
        if (rel > worst_rt) { worst_rt = rel; worst_p = p; }
    }
    check(worst_rt < 1e-11, "aller-retour cdf/quantile");
    std::printf("  aller-retour : %.3e (pire a p = %.2e)\n", worst_rt, worst_p);

    // Ce qui echouait en Python
    for (double n : {1e15, 1e16, 1e20, 1e100, 1e300}) {
        const double v = math::norm_quantile_upper(1.0 / n);
        check(std::isfinite(v) && v > 0.0, "quantile_upper(1e" + std::to_string((int)std::log10(n)) + ")");
    }
    check(math::norm_cdf(-10.0) > 0.0, "cdf(-10) strictement positive");
    check_close(math::norm_cdf(-10.0), 7.619853024160526e-24, 1e-14, "cdf(-10) valeur");
}

static void test_moments() {
    std::vector<double> xs;
    for (int i = 1; i <= 500; ++i)
        xs.push_back(i / 1000.0 - 0.5 + double(i) * i / 700000.0);
    const auto m = math::compute_moments(xs);
    check_close(m.mean,     ref::MOM_MEAN,     1e-13, "moyenne");
    check_close(m.variance, ref::MOM_VARIANCE, 1e-13, "variance");
    check_close(m.skewness, ref::MOM_SKEW,     1e-12, "asymetrie");
    check_close(m.kurtosis, ref::MOM_KURT,     1e-12, "kurtosis");
    std::printf("  moments  : moyenne, variance, asymetrie, kurtosis a <1e-12\n");

    std::vector<double> plat(100, 0.01);
    check(sharpe_ratio(plat) == 0.0, "serie constante -> Sharpe nul (pas 1e15)");
}

// ------------------------------------------------------------------ domaine
static Fill mk(Side s, double q, double p, double c = 0.0) {
    Fill f; f.order_id = 1; f.side = s; f.qty = q; f.price = p;
    f.is_maker = true; f.commission = c; return f;
}

static void test_portfolio() {
    { Portfolio pf; pf.apply(mk(Side::Buy, 100, 10.0));
      check(pf.position() == 100 && pf.avg_price() == 10.0 && pf.cash() == -1000.0,
            "achat simple"); }
    { Portfolio pf; pf.apply(mk(Side::Buy, 100, 10.0)); pf.apply(mk(Side::Sell, 100, 11.0));
      check_close(pf.realised_pnl(), 100.0, 1e-12, "aller-retour gagnant"); }
    { Portfolio pf; pf.apply(mk(Side::Buy, 100, 10.0)); pf.apply(mk(Side::Buy, 100, 12.0));
      check_close(pf.avg_price(), 11.0, 1e-12, "moyenne ponderee"); }
    { Portfolio pf; pf.apply(mk(Side::Buy, 100, 10.0)); pf.apply(mk(Side::Sell, 40, 12.0));
      check_close(pf.avg_price(), 10.0, 1e-12, "reduction : moyenne inchangee");
      check_close(pf.realised_pnl(), 80.0, 1e-12, "reduction : resultat realise"); }
    { Portfolio pf; pf.apply(mk(Side::Buy, 100, 10.0)); pf.apply(mk(Side::Sell, 150, 12.0));
      check_close(pf.position(), -50.0, 1e-12, "inversion : position");
      check_close(pf.realised_pnl(), 200.0, 1e-12, "inversion : 100x2, pas 150x2");
      check_close(pf.avg_price(), 12.0, 1e-12, "inversion : nouvelle moyenne"); }
}

static void test_costs() {
    CostModel c{0.20, 2.00, -1.0};
    check_close(c.commission(10'000, false), 2.0, 1e-12, "plancher a 10k");
    check_close(c.commission(100'000, false), 2.0, 1e-12, "egalite exacte a 100k");
    check_close(c.commission(1'000'000, false), 20.0, 1e-12, "taux au-dela");
    // Le plancher mord jusqu'a exactement 2 / 0.000020 = 100 000
    check_close(2.0 / (0.20 / 10'000.0), 100'000.0, 1e-12, "seuil du plancher");
}

static void test_carry() {
    carry::Simulator s{{25.0, 2.0, 2.0, 0.005, true, 2.0}};
    check_close(s.liquidation_price(100.0), 100.0 * 1.5 / 1.005, 1e-12, "prix de liquidation 2:1");
    const double hausse = s.liquidation_price(100.0) / 100.0 - 1.0;
    check(hausse > 0.48 && hausse < 0.50, "plafond UE : ~49 % de hausse requise");

    carry::Simulator cross{{25.0, 2.0, 2.0, 0.005, false, 2.0}};
    check(std::isinf(cross.liquidation_price(100.0)), "marge croisee : seuil infini");

    // Funding positif sur 90 jours, prix plat
    std::vector<std::pair<std::int64_t, double>> px;
    for (int i = 0; i < 90 * 24; ++i) px.emplace_back(std::int64_t(i) * 3'600'000'000'000LL, 100.0);
    std::vector<carry::FundingEvent> fd;
    for (int i = 0; i < 90 * 3; ++i)
        fd.push_back({std::int64_t(i + 1) * 28'800'000'000'000LL, 1.0, 100.0});
    const auto r = s.run(px, fd, 10'000.0);
    check(!r.liquidated, "funding positif, prix plat : pas de liquidation");
    check(r.net_capital_bps > 0.0, "funding positif : resultat positif");
    check_close(r.notional, 10'000.0 / 1.5, 1e-9, "efficience du capital 2:1");
}

static void test_metrics() {
    std::vector<double> r = {0.01, 0.02, -0.01, 0.03};
    check_close(sharpe_ratio(r), 0.0125 / std::sqrt(8.75e-4 / 3.0), 1e-12, "Sharpe calcule a la main");

    std::vector<double> long_r;
    for (int i = 0; i < 120; ++i) long_r.push_back(r[i % 4]);
    check(deflated_sharpe_ratio(long_r, 100) < probabilistic_sharpe_ratio(long_r),
          "le DSR est plus severe que le PSR");
    check(deflated_sharpe_ratio(long_r, 5) > deflated_sharpe_ratio(long_r, 10'000),
          "le DSR decroit avec le nombre d'essais");
    check(std::isfinite(deflated_sharpe_ratio(long_r, 1e20)),
          "DSR fini a 1e20 essais (echouait en Python)");
    check(expected_max_sharpe(1.0, 0.01) == 0.0, "un seul essai ne deflate pas");
    check(expected_max_sharpe(2, 0.01) < expected_max_sharpe(1000, 0.01),
          "le seuil du hasard croit avec les essais");

    std::vector<double> eq = {100, 120, 90, 130};
    const auto dd = max_drawdown(eq);
    check_close(dd.depth, 0.25, 1e-12, "drawdown maximal");
    check(dd.peak_idx == 1 && dd.trough_idx == 2, "indices du drawdown");
}

int main() {
    std::printf("=== TESTS C++ (references mpmath, 300 chiffres) ===\n\n");
    std::printf("Mathematiques :\n");   test_normal(); test_moments();
    std::printf("\nDomaine :\n");        test_portfolio(); test_costs();
    std::printf("Carry et metriques :\n"); test_carry(); test_metrics();
    std::printf("\n%d passes, %d echecs\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
