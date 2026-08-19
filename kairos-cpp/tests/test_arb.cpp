// Tests du detecteur N-jambes.
// Comptages de cycles CALCULES par la formule C(n,k) x (k-1)!, jamais recopies.
#include "kairos/arb/detector.hpp"
#include <cmath>
#include <cstdio>
#include <string>

static int g_pass = 0, g_fail = 0;
static void check(bool ok, const std::string& n, const std::string& d = "") {
    if (ok) ++g_pass;
    else { ++g_fail; std::printf("  ECHEC  %s%s%s\n", n.c_str(),
                                 d.empty() ? "" : " — ", d.c_str()); }
}
static void check_close(double got, double want, double tol, const std::string& n) {
    const bool ok = std::abs(got - want) <= tol;
    check(ok, n, ok ? "" : "obtenu " + std::to_string(got) + " attendu " + std::to_string(want));
}

using namespace kairos::arb;

static long long binom(int n, int k) {
    long long r = 1;
    for (int i = 1; i <= k; ++i) r = r * (n - k + i) / i;
    return r;
}
static long long fact(int k) { long long r = 1; for (int i = 2; i <= k; ++i) r *= i; return r; }

// ---------------------------------------------------------------- comptage
static void test_comptage_cycles() {
    const char* devises[] = {"USD","EUR","GBP","JPY","CHF","AUD","CAD"};
    Detector d;
    // Graphe COMPLET : toutes les paires cotees
    for (int i = 0; i < 7; ++i)
        for (int j = i + 1; j < 7; ++j)
            d.add_pair({devises[i], devises[j], 1.0, 1.0});

    check(d.n_currencies() == 7, "7 devises");
    check(d.n_pairs() == 21, "21 paires sur graphe complet");

    std::printf("  Graphe complet a 7 devises :\n");
    for (int k = 3; k <= 5; ++k) {
        const auto cyc = d.enumerate_cycles(k);
        const long long attendu = binom(7, k) * fact(k - 1);   // CALCULE
        std::printf("    %d jambes : %5zu cycles   (formule C(7,%d)x%d! = %lld)\n",
                    k, cyc.size(), k, k - 1, attendu);
        check(static_cast<long long>(cyc.size()) == attendu,
              "comptage " + std::to_string(k) + " jambes");
    }
}

// ---------------------------------------------------------------- convention
static void test_convention_de_cotation() {
    // GBP/USD = 1,2715 signifie « 1,2715 USD par GBP ».
    Detector d;
    d.add_pair({"GBP", "USD", 1.27150, 1.27160});

    const auto gu = d.resolve("GBP", "USD");   // vendre GBP -> bid
    const auto ug = d.resolve("USD", "GBP");   // acheter GBP -> 1 / ask
    check(gu.has_value() && ug.has_value(), "les deux sens sont resolus");
    check(!gu->inverted && ug->inverted, "seul USD->GBP est inverse");
    check_close(gu->rate, 1.27150, 1e-12, "GBP->USD utilise le bid");
    check_close(ug->rate, 1.0 / 1.27160, 1e-12, "USD->GBP utilise 1/ask");

    // L'aller-retour doit couter le spread, pas rapporter 6 000 bps.
    const double produit = gu->rate * ug->rate;
    const double dev_bps = (produit - 1.0) * 10'000.0;
    std::printf("  aller-retour GBP->USD->GBP : %+.4f bps (spread cote %.4f bps)\n",
                dev_bps, 0.5 * (1.27150 + 1.27160) > 0
                    ? (1.27160 - 1.27150) / (0.5 * (1.27150 + 1.27160)) * 10'000.0 : 0.0);
    check(dev_bps < 0.0, "l'aller-retour PERD le spread");
    check(dev_bps > -1.0, "et ne perd que le spread, soit moins de 1 bps");

    // Le bug reel : multiplier par le taux dans les DEUX sens.
    const double naif = 1.27150 * 1.27150;
    const double dev_naif = (naif - 1.0) * 10'000.0;
    std::printf("  version naive (taux x taux)  : %+.0f bps  <- deviation FICTIVE\n", dev_naif);
    check(dev_naif > 6000.0, "le bug naif produit bien ~+6 200 bps");
    check(std::abs(dev_bps) < 1.0 && dev_naif > 6000.0,
          "l'ecart entre correct et naif depasse 6 000 bps");
}

// ---------------------------------------------------------------- couts
static void test_modele_de_couts() {
    // Doit reproduire le tableau du rapport, 3 jambes, spread 0,28 bps
    CostModel c{0.20, 2.00, 0.0};
    struct { double notional, attendu; } cas[] = {
        {5'000, 12.42}, {10'000, 6.42}, {25'000, 2.82},
        {50'000, 1.62}, {100'000, 1.02}, {1'000'000, 1.02}};
    std::printf("  Cout de boucle a 3 jambes (spread 0,28 bps) :\n");
    for (const auto& k : cas) {
        const double total = 3.0 * c.leg_cost_bps(k.notional, 0.28);
        std::printf("    %9.0f USD -> %6.3f bps (rapport : %.2f)\n", k.notional, total, k.attendu);
        check_close(total, k.attendu, 1e-9, "cout a " + std::to_string((long)k.notional));
    }
    // Le plancher mord jusqu'a exactement 2 / 0,000020 = 100 000
    check_close(2.0 / (0.20 / 10'000.0), 100'000.0, 1e-9, "seuil du plancher");
}

// ---------------------------------------------------------------- detection
static void test_detection() {
    Detector d;
    // Triangle parfaitement coherent : EUR/USD x USD/JPY = EUR/JPY
    d.add_pair({"EUR", "USD", 1.08000, 1.08002});
    d.add_pair({"USD", "JPY", 157.000, 157.002});
    d.add_pair({"EUR", "JPY", 1.08 * 157.0, 1.08 * 157.0 * 1.00001});

    const auto ev = d.evaluate({0, 1, 2});
    check(ev.has_value(), "le triangle est evaluable");

    // Aucun profit net attendu : les frais dominent
    const auto opps = d.scan(CostModel{0.20, 2.00, 0.0}, 10'000, 3, 3, true);
    std::printf("  triangle coherent, ticket 10k : %zu opportunite(s) nette(s)\n", opps.size());
    check(opps.empty(), "aucune opportunite nette sur un triangle coherent");

    // Avec only_profitable = false on voit le brut ET le net
    const auto tous = d.scan(CostModel{0.20, 2.00, 0.0}, 10'000, 3, 3, false);
    check(!tous.empty(), "le mode non filtre expose toutes les boucles");
    for (const auto& o : tous)
        check(o.net_bps <= o.gross_bps, "le net ne depasse jamais le brut");

    // Dislocation injectee assez grande pour survivre aux frais
    Detector d2;
    d2.add_pair({"EUR", "USD", 1.08000, 1.08002});
    d2.add_pair({"USD", "JPY", 157.000, 157.002});
    d2.add_pair({"EUR", "JPY", 1.08 * 157.0 * 1.002, 1.08 * 157.0 * 1.00201});
    const auto found = d2.scan(CostModel{0.20, 2.00, 0.0}, 100'000, 3, 3, true);
    std::printf("  dislocation de +20 bps injectee : %zu opportunite(s)\n", found.size());
    check(!found.empty(), "une dislocation de 20 bps est detectee a 100k");
    if (!found.empty()) {
        check(found.front().net_bps > 0.0, "et son net est positif");
        check(found.front().n_legs() == 3, "boucle a 3 jambes");
        std::printf("    meilleure : %s | brut %+.2f | cout %.2f | NET %+.2f bps\n",
                    found.front().path_string().c_str(), found.front().gross_bps,
                    found.front().cost_bps, found.front().net_bps);
    }
}

static void test_graphe_partiel() {
    // Devise isolee : aucun cycle ne doit la traverser
    Detector d;
    d.add_pair({"EUR", "USD", 1.08, 1.0801});
    d.add_pair({"USD", "JPY", 157.0, 157.01});
    d.add_pair({"EUR", "JPY", 169.56, 169.57});
    d.add_pair({"AUD", "NZD", 1.09, 1.0901});   // composante deconnectee
    const auto c3 = d.enumerate_cycles(3);
    std::printf("  graphe a 2 composantes : %zu cycle(s) a 3 jambes\n", c3.size());
    check(c3.size() == 2, "seuls les 2 sens du triangle connecte sont retenus");
}

// ---------------------------------------------------------------- convention
// NON-REGRESSION : le spread etait compte deux fois.
static void test_pas_de_double_comptage() {
    // Triangle PARFAITEMENT coherent sur les mid, spread de 0,28 bps par paire.
    const double m1 = 1.08, m2 = 157.0, m3 = m1 * m2;
    const double s = 0.28;
    auto ba = [&](double m) { return std::pair{m * (1 - s / 20000.0), m * (1 + s / 20000.0)}; };
    const auto [b1, a1] = ba(m1); const auto [b2, a2] = ba(m2); const auto [b3, a3] = ba(m3);

    Detector d;
    d.add_pair({"EUR", "USD", b1, a1});
    d.add_pair({"USD", "JPY", b2, a2});
    d.add_pair({"EUR", "JPY", b3, a3});

    // 1. La deviation executable contient DEJA les trois demi-spreads.
    const auto ev = d.evaluate({0, 1, 2});
    check(ev.has_value(), "triangle evaluable");
    const double brut = ev->second;
    std::printf("  deviation executable sur triangle parfait : %+.6f bps\n", brut);
    check_close(brut, -3.0 * s / 2.0, 1e-4, "le brut vaut -3 x demi-spread");

    // 2. En base Executable, le cout ne doit contenir QUE la commission.
    const CostModel c{0.20, 2.00, 0.0};
    const auto exec = d.scan(c, 10'000, 3, 3, false, DeviationBasis::Executable);
    check(!exec.empty(), "balayage executable non vide");
    check_close(exec.front().cost_bps, 3.0 * 2.00, 1e-9, "cout executable = 3 x commission");

    // 3. En base Mid, le demi-spread revient — c'est la convention du rapport.
    const auto mid = d.scan(c, 10'000, 3, 3, false, DeviationBasis::Mid);
    check_close(mid.front().cost_bps, 6.42, 1e-9, "cout Mid = 6,42 bps (tableau du rapport)");

    // 4. L'ecart entre les deux conventions vaut exactement 3 x demi-spread.
    const double ecart = mid.front().cost_bps - exec.front().cost_bps;
    std::printf("  ecart entre conventions : %.6f bps (attendu %.6f)\n", ecart, 3.0 * s / 2.0);
    check_close(ecart, 3.0 * s / 2.0, 1e-9, "l'ecart est bien le triple demi-spread");

    // 5. L'invariant : net = brut - commission seule, sur CHAQUE boucle.
    //    Comparer a `brut` mesure plus haut serait faux : les deux sens de la
    //    boucle ont des deviations legerement differentes, et front() est trie
    //    par net decroissant — ce n'est pas forcement le sens evalue en 1.
    for (const auto& o : exec)
        check_close(o.net_bps, o.gross_bps - 6.00, 1e-9, "net = brut - commission");
    std::printf("  net de la meilleure boucle : %+.4f bps  "
                "(l'ancien code annoncait %+.4f)\n",
                exec.front().net_bps, exec.front().gross_bps - 6.42);

    // 6. Les deux sens different bien, ce qui justifie la remarque ci-dessus.
    check(exec.size() == 2, "les deux sens sont presents");
    if (exec.size() == 2)
        std::printf("  les deux sens : %+.6f et %+.6f bps de brut\n",
                    exec[0].gross_bps, exec[1].gross_bps);
}

int main() {
    std::printf("=== TESTS DU DETECTEUR N-JAMBES ===\n\n");
    std::printf("Comptage :\n");        test_comptage_cycles();
    std::printf("\nConvention de cotation :\n"); test_convention_de_cotation();
    std::printf("\nCouts :\n");          test_modele_de_couts();
    std::printf("\nDetection :\n");      test_detection();
    std::printf("\nGraphe partiel :\n"); test_graphe_partiel();
    std::printf("\nBase de deviation (non-regression) :\n"); test_pas_de_double_comptage();
    std::printf("\n%d passes, %d echecs\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
