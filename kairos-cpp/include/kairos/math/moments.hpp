#pragma once
// Moments statistiques.
//
// CHOIX JUSTIFIE PAR LA MESURE, PAS PAR LA REPUTATION DES ALGORITHMES.
//
// L'algorithme en ligne de Pebay pour les moments d'ordre eleve est souvent
// presente comme superieur. Confronte a une reference exacte en arithmetique
// rationnelle sur des rendements realistes, il ne l'est PAS :
//
//     donnees centrees      naif 3.3e-14   Pebay 4.3e-14
//     decalees de 1e6       naif 2.6e-06   Pebay 1.1e-06
//     decalees de 1e8       naif 8.0e-05   Pebay 1.3e-04   <- Pebay est pire
//
// Les rendements financiers sont naturellement centres autour de zero, donc le
// cas degrade ne se presente pas. On garde la methode a deux passes, plus simple
// et plus rapide, et on CENTRE explicitement — ce qui est le vrai correctif,
// commun aux deux methodes.
//
// La variance utilise le diviseur (n-1) : estimateur non biaise, coherent avec
// le Sharpe. La skewness et le kurtosis utilisent n : conventions du PSR.

#include <cmath>
#include <span>
#include <stdexcept>

namespace kairos::math {

struct Moments {
    std::size_t n{};
    double mean{};
    double variance{};      // non biaisee, diviseur (n-1)
    double stddev{};
    double skewness{};
    double kurtosis{};      // BRUT : vaut 3 pour une loi normale, pas 0
};

// Un ecart-type indiscernable de zero, a l'echelle des donnees.
//
// Tester sd == 0 ne suffit pas : sur une serie constante, l'arithmetique
// flottante laisse une variance residuelle de l'ordre de 1e-18. Le Sharpe
// calcule vaut alors 1e15 au lieu de zero — et un Sharpe absurde ressemble
// a une decouverte avant de ressembler a un bug.
[[nodiscard]] inline bool numerically_flat(double sd, std::span<const double> xs) noexcept {
    double scale = 0.0;
    for (double x : xs) scale = std::max(scale, std::abs(x));
    if (scale == 0.0) scale = 1.0;
    return sd <= scale * 1e-12;
}

[[nodiscard]] inline Moments compute_moments(std::span<const double> xs) {
    Moments m;
    m.n = xs.size();
    if (m.n == 0) return m;

    // Passe 1 — moyenne
    double s = 0.0;
    for (double x : xs) s += x;
    m.mean = s / static_cast<double>(m.n);

    // Passe 2 — moments centres. Le centrage explicite est le correctif qui
    // compte : il ramene les valeurs autour de zero avant l'elevation aux
    // puissances, la ou l'erreur relative serait amplifiee.
    double m2 = 0.0, m3 = 0.0, m4 = 0.0;
    for (double x : xs) {
        const double d  = x - m.mean;
        const double d2 = d * d;
        m2 += d2;
        m3 += d2 * d;
        m4 += d2 * d2;
    }
    const double N = static_cast<double>(m.n);

    m.variance = (m.n > 1) ? m2 / (N - 1.0) : 0.0;
    m.stddev   = std::sqrt(m.variance);

    const double m2n = m2 / N;
    if (m2n > 0.0) {
        m.skewness = (m3 / N) / std::pow(m2n, 1.5);
        m.kurtosis = (m4 / N) / (m2n * m2n);
    } else {
        m.skewness = 0.0;
        m.kurtosis = 3.0;
    }
    return m;
}

} // namespace kairos::math
