#pragma once
// Loi normale — precision machine.
//
// DEUX DEFAUTS MESURES DANS L'IMPLEMENTATION PYTHON, CORRIGES ICI.
//
// 1. LA QUEUE DE LA FONCTION DE REPARTITION.
//    La forme repandue 0.5*(1 + erf(x/V2)) subit une annulation catastrophique
//    quand x est tres negatif : erf tend vers -1, et 1 + (-1) perd tous les
//    chiffres significatifs. Mesure a x = -10 : la forme naive renvoie
//    EXACTEMENT 0.0 alors que la valeur vraie est 7.61985302416059e-24.
//    Erreur relative : 100 %.
//    On utilise donc 0.5*erfc(-x/V2), exacte sur toute la plage.
//
// 2. LE QUANTILE PRES DE 1.
//    Calculer Phi^-1(1 - 1/N) echoue des que 1 - 1/N s'arrondit a 1.0, ce qui
//    survient pour N >= 1e16 en double. Mesure : echec pur et simple, et deja
//    7e-4 d'erreur a N = 1e15.
//    On expose donc quantile_upper(q) = -quantile(q), qui garde l'argument
//    loin de 1 et couvre tout N, jusqu'a 1e300.
//
// Le quantile utilise l'approximation rationnelle d'Acklam (~1.15e-9 relatif)
// suivie d'UN pas de Halley, ce qui porte l'erreur au niveau de l'epsilon
// machine (~1e-16 relatif). Le pas de Halley est cubiquement convergent : un
// seul suffit, un second n'apporterait rien de mesurable.

#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>

namespace kairos::math {

inline constexpr double SQRT2      = 1.41421356237309504880168872420969808;
inline constexpr double SQRT2PI    = 2.50662827463100050241576528481104525;
inline constexpr double INV_SQRT2  = 0.70710678118654752440084436210484904;
inline constexpr double EULER_MASCHERONI = 0.57721566490153286060651209008240243;

// 1/V2 en double-double. La somme HI + LO represente 1/V2 a 2.9e-33 pres,
// la ou le double seul plafonne a 1.1e-16.
inline constexpr double INV_SQRT2_HI = 7.07106781186547572737e-01;
inline constexpr double INV_SQRT2_LO = -4.83364665672645672553e-17;
inline constexpr double TWO_OVER_SQRTPI = 1.12837916709551257389615890312155;

namespace detail {
// erfc(a) ou l'argument vrai est a + da, avec da minuscule.
//
// POURQUOI CE DETOUR EST NECESSAIRE
//   Mesure : std::erfc est exacte a 2.3e-15, mais norm_cdf(-37) affichait 8.8e-14
//   d'erreur. L'ecart ne vient donc PAS de erfc — il vient de l'argument.
//   Dans la queue, erfc(a) se comporte comme exp(-a^2) : une erreur relative eps
//   sur a produit une erreur relative 2.a^2.eps sur le resultat. A a = 26, le
//   facteur d'amplification vaut ~1370.
//
//   On calcule donc l'argument en double-double (l'erreur exacte du produit est
//   recuperee par fma), puis on corrige au premier ordre :
//       erfc(a + da) ~ erfc(a) - da . (2/Vpi) . exp(-a^2)
[[nodiscard]] inline double erfc_corrected(double a, double da) noexcept {
    const double base = std::erfc(a);
    if (da == 0.0 || base == 0.0) return base;
    return base - da * TWO_OVER_SQRTPI * std::exp(-a * a);
}

// -x/V2 evalue en double-double : renvoie (partie haute, residu exact).
[[nodiscard]] inline std::pair<double, double> scaled_arg(double x) noexcept {
    const double a  = -x * INV_SQRT2_HI;
    const double e1 = std::fma(-x, INV_SQRT2_HI, -a);   // residu exact du produit
    const double e2 = -x * INV_SQRT2_LO;                // terme basse precision
    return {a, e1 + e2};
}
} // namespace detail

// P(X <= x). Exacte jusqu'a ~1e-308, sans annulation ni amplification d'argument.
[[nodiscard]] inline double norm_cdf(double x) noexcept {
    const auto [a, da] = detail::scaled_arg(x);
    return 0.5 * detail::erfc_corrected(a, da);
}

// P(X > x). Forme complementaire directe, sans 1 - cdf(x).
[[nodiscard]] inline double norm_sf(double x) noexcept {
    const auto [a, da] = detail::scaled_arg(-x);
    return 0.5 * detail::erfc_corrected(a, da);
}

[[nodiscard]] inline double norm_pdf(double x) noexcept {
    return std::exp(-0.5 * x * x) / SQRT2PI;
}

namespace detail {
// Coefficients d'Acklam
inline constexpr double A[6] = {-3.969683028665376e+01,  2.209460984245205e+02,
                                -2.759285104469687e+02,  1.383577518672690e+02,
                                -3.066479806614716e+01,  2.506628277459239e+00};
inline constexpr double B[5] = {-5.447609879822406e+01,  1.615858368580409e+02,
                                -1.556989798598866e+02,  6.680131188771972e+01,
                                -1.328068155288572e+01};
inline constexpr double C[6] = {-7.784894002430293e-03, -3.223964580411365e-01,
                                -2.400758277161838e+00, -2.549732539343734e+00,
                                 4.374664141464968e+00,  2.938163982698783e+00};
inline constexpr double D[4] = { 7.784695709041462e-03,  3.224671290700398e-01,
                                 2.445134137142996e+00,  3.754408661907416e+00};
inline constexpr double P_LOW  = 0.02425;
inline constexpr double P_HIGH = 1.0 - P_LOW;

[[nodiscard]] inline double acklam(double p) noexcept {
    if (p < P_LOW) {
        const double q = std::sqrt(-2.0 * std::log(p));
        return (((((C[0]*q + C[1])*q + C[2])*q + C[3])*q + C[4])*q + C[5]) /
               ((((D[0]*q + D[1])*q + D[2])*q + D[3])*q + 1.0);
    }
    if (p > P_HIGH) {
        const double q = std::sqrt(-2.0 * std::log(1.0 - p));
        return -(((((C[0]*q + C[1])*q + C[2])*q + C[3])*q + C[4])*q + C[5]) /
                ((((D[0]*q + D[1])*q + D[2])*q + D[3])*q + 1.0);
    }
    const double q = p - 0.5, r = q * q;
    return (((((A[0]*r + A[1])*r + A[2])*r + A[3])*r + A[4])*r + A[5]) * q /
           (((((B[0]*r + B[1])*r + B[2])*r + B[3])*r + B[4])*r + 1.0);
}
} // namespace detail

// Phi^-1(p). Acklam + un pas de Halley -> precision machine.
[[nodiscard]] inline double norm_quantile(double p) {
    if (!(p > 0.0) || !(p < 1.0)) {
        if (p == 0.0) return -std::numeric_limits<double>::infinity();
        if (p == 1.0) return  std::numeric_limits<double>::infinity();
        throw std::domain_error("norm_quantile : p doit etre dans ]0, 1[");
    }
    double x = detail::acklam(p);

    // Raffinement de Halley. On evalue l'ecart avec erfc pour ne pas
    // reintroduire l'annulation que l'on vient d'eviter.
    const double e = norm_cdf(x) - p;
    const double u = e * SQRT2PI * std::exp(0.5 * x * x);
    x -= u / (1.0 + 0.5 * x * u);
    return x;
}

// Phi^-1(1 - q), calcule SANS jamais former 1 - q.
//
// C'est la fonction a utiliser des qu'on cherche un quantile proche de 1 :
// pour q = 1e-20, l'appel naif norm_quantile(1 - 1e-20) echoue puisque
// 1 - 1e-20 vaut exactement 1.0 en double. Ici l'argument reste 1e-20.
[[nodiscard]] inline double norm_quantile_upper(double q) {
    return -norm_quantile(q);
}

} // namespace kairos::math
