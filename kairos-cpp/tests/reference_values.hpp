#pragma once
// GENERE par mpmath a 300 chiffres — ne pas editer a la main.
//
// Une seule valeur est retouchee : Phi^-1(0.5), ramenee a 0.0 exact. findroot
// converge vers un denormal (-1.37e-308) la ou la valeur vraie est exactement
// zero ; comparer en relatif a un denormal donne 100 % d'erreur sur un resultat
// pourtant juste.
//
// Recopier des valeurs de memoire est exactement ce qui a produit une fausse
// alerte lors du premier essai : la reference etait erronee de 1.67e-7, pas
// le code. Une valeur de reference doit etre CALCULEE, jamais rappelee.
namespace ref {
struct CdfCase { double x, expected; };
inline constexpr CdfCase CDF[] = {
    {0.0, 0.5},
    {-1.0, 0.158655253931457051},
    {-2.5, 0.00620966532577613517},
    {-3.0, 0.00134989803163009453},
    {-6.0, 9.86587645037698141e-10},
    {-10.0, 7.61985302416052607e-24},
    {-20.0, 2.7536241186062337e-89},
    {-37.0, 5.72557122252457682e-300},
    {1.0, 0.841344746068542949},
    {3.0, 0.998650101968369905},
};
struct QCase { double p, expected; };
inline constexpr QCase QUANTILE[] = {
    {0.5, 0.0},
    {0.975, 1.95996398454005424},
    {0.025, -1.95996398454005424},
    {0.001, -3.09023230616781354},
    {1e-6, -4.75342430882289895},
    {1e-10, -6.3613409024040562},
    {1e-50, -14.933337534788489},
    {1e-100, -21.2734535609653243},
    {1e-200, -30.2055941795796431},
};
// Serie deterministe x_i = i/1000 - 0.5 + i^2/700000, i = 1..500
inline constexpr double MOM_MEAN     = -0.130095;
inline constexpr double MOM_VARIANCE = 0.0621592489285714286;
inline constexpr double MOM_SKEW     = 0.284282821196178466;
inline constexpr double MOM_KURT     = 1.8658501904228535;
}  // namespace ref
