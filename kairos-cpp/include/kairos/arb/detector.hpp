#pragma once
// Detecteur d'arbitrage a N jambes sur le graphe des devises.
//
// LE PIEGE CENTRAL : LA CONVENTION DE COTATION
//   Une paire FX porte un sens. GBP/USD vaut ~1,2715 et signifie « 1,2715 USD
//   par GBP », jamais l'inverse. Convertir GBP -> USD se fait donc en
//   MULTIPLIANT par le bid ; convertir USD -> GBP en DIVISANT par le ask.
//
//   Une implementation naive qui multiplie par le taux dans les deux sens
//   calcule, pour l'aller-retour GBP -> USD -> GBP, un produit de 1,2715^2 =
//   1,6167, soit une deviation fictive de +6 167 bps. Bug reel, deja rencontre
//   sur ce projet. Le test tst_convention_de_cotation le reproduit.
//
// PHILOSOPHIE : ON NE PUBLIE QUE LE NET
//   La mesure fondatrice du projet est 63,8 % d'instants bruts positifs pour
//   0,00 % au-dessus du seuil de cout. Un detecteur qui expose le brut invite
//   a se tromper. `scan()` ne retourne donc que des opportunites NETTES de frais,
//   et `Opportunity` porte les trois chiffres pour que le lecteur voie l'ecart.

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <numeric>
#include <optional>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace kairos::arb {

// ---------------------------------------------------------------- cotation
struct PairQuote {
    std::string base;      // ex. "GBP"
    std::string quote;     // ex. "USD"  -> le prix s'entend en USD par GBP
    double bid{};
    double ask{};

    [[nodiscard]] bool valid() const noexcept {
        return bid > 0.0 && ask > 0.0 && ask >= bid;
    }
    [[nodiscard]] double mid() const noexcept { return 0.5 * (bid + ask); }
    [[nodiscard]] double spread_bps() const noexcept {
        const double m = mid();
        return m > 0.0 ? (ask - bid) / m * 10'000.0 : 0.0;
    }
};

// Un pas de conversion, avec le sens resolu.
struct Leg {
    std::string from, to;
    std::string pair;          // etiquette lisible, ex. "GBP/USD"
    double rate{};             // multiplicateur applique au montant
    bool inverted{};           // true si on a divise par le ask

    [[nodiscard]] std::string describe() const {
        return from + "->" + to + " (" + pair + (inverted ? ", inverse)" : ")");
    }
};

// SUR QUELLE BASE LA DEVIATION EST-ELLE MESUREE ?
//
// Cette distinction n'est pas un detail de presentation : la confondre fait
// compter le spread DEUX FOIS, et le bug est silencieux.
//
//   Mid        — la deviation est calculee sur les prix moyens. Le spread n'y
//                figure pas, il faut donc l'ajouter au cout :
//                    cout = n x (commission + demi-spread)
//                C'est la convention du rapport et de la litterature, ou les
//                deviations triangulaires sont citees sur les prix cotes.
//
//   Executable — la deviation est calculee sur bid/ask, comme le fait resolve().
//                Le spread est DEJA paye dans le produit des taux. Le seul cout
//                restant est la commission :
//                    cout = n x commission
//
// Mesure : sur un triangle parfaitement coherent sur les mid, avec 0,28 bps de
// spread par paire, la deviation executable vaut -0,420 bps, soit exactement
// -3 x demi-spread. Le spread est bien deja compte.
//
// La premiere version de scan() melangeait les deux : deviation executable,
// cout de convention Mid. Elle sous-estimait le net de 0,420 bps a 3 jambes,
// et l'erreur croit avec le spread — 7,5 bps sur une paire a 5 bps.
enum class DeviationBasis { Mid, Executable };

struct CostModel {
    double commission_bps{0.20};
    double commission_floor{2.00};
    double slippage_bps{0.0};

    // Cout d'UNE jambe, en bps du notionnel.
    // spread_bps ne doit etre non nul QUE en convention Mid.
    [[nodiscard]] double leg_cost_bps(double notional, double spread_bps) const noexcept {
        const double comm = std::max(commission_bps,
                                     commission_floor / notional * 10'000.0);
        return comm + spread_bps / 2.0 + slippage_bps;
    }
};

struct Opportunity {
    std::vector<Leg> legs;
    double gross_bps{};        // deviation brute : (produit - 1) x 10 000
    double cost_bps{};         // cout total de la boucle
    double net_bps{};          // gross - cost : LE SEUL chiffre qui decide
    double notional{};

    [[nodiscard]] std::size_t n_legs() const noexcept { return legs.size(); }
    [[nodiscard]] bool profitable() const noexcept { return net_bps > 0.0; }

    [[nodiscard]] std::string path_string() const {
        if (legs.empty()) return {};
        std::string s = legs.front().from;
        for (const auto& l : legs) s += " -> " + l.to;
        return s;
    }
};

// ---------------------------------------------------------------- detecteur
class Detector {
public:
    // Une paire cotee rend les DEUX sens de conversion possibles, mais avec des
    // formules differentes : c'est precisement ce que la version naive rate.
    void add_pair(const PairQuote& q) {
        if (!q.valid())
            throw std::invalid_argument("cotation invalide pour " + q.base + "/" + q.quote);
        const int b = intern(q.base), s = intern(q.quote);
        quotes_[{b, s}] = q;
    }

    [[nodiscard]] std::size_t n_currencies() const noexcept { return names_.size(); }
    [[nodiscard]] std::size_t n_pairs() const noexcept { return quotes_.size(); }

    // Resolution d'une arete from -> to, en respectant la convention.
    [[nodiscard]] std::optional<Leg> resolve(int from, int to) const {
        // Cas direct : la paire est cotee (from/to), on VEND from -> bid
        if (const auto it = quotes_.find({from, to}); it != quotes_.end()) {
            return Leg{names_[from], names_[to],
                       names_[from] + "/" + names_[to], it->second.bid, false};
        }
        // Cas inverse : la paire est cotee (to/from), on ACHETE to -> 1 / ask
        if (const auto it = quotes_.find({to, from}); it != quotes_.end()) {
            return Leg{names_[from], names_[to],
                       names_[to] + "/" + names_[from], 1.0 / it->second.ask, true};
        }
        return std::nullopt;
    }

    [[nodiscard]] std::optional<Leg> resolve(const std::string& from,
                                             const std::string& to) const {
        const auto f = index_of(from), t = index_of(to);
        if (!f || !t) return std::nullopt;
        return resolve(*f, *t);
    }

    // Enumeration des cycles diriges distincts de longueur k.
    //
    // DEFINITION EXPLICITE, parce qu'elle determine le comptage :
    //   - les rotations sont identifiees (A->B->C->A vaut B->C->A->B)
    //   - les deux SENS sont distincts (A->B->C->A != A->C->B->A)
    //   - chaque devise apparait au plus une fois
    // Sur un graphe complet a n devises cela donne C(n,k) x (k-1)! cycles :
    // 70 a 3 jambes, 210 a 4, 504 a 5 pour n = 7. Ces valeurs sont CALCULEES
    // par le test, pas recopiees.
    [[nodiscard]] std::vector<std::vector<int>> enumerate_cycles(int k) const {
        std::vector<std::vector<int>> out;
        const int n = static_cast<int>(names_.size());
        if (k < 2 || k > n) return out;

        std::vector<int> combo(k);
        std::vector<int> idx(n);
        std::iota(idx.begin(), idx.end(), 0);

        // Toutes les combinaisons de k devises
        std::vector<bool> mask(n, false);
        std::fill(mask.begin(), mask.begin() + k, true);
        std::vector<int> chosen;
        chosen.reserve(k);
        std::vector<int> sorted_mask_order(n);
        std::iota(sorted_mask_order.begin(), sorted_mask_order.end(), 0);

        std::vector<bool> m(n, false);
        std::fill(m.begin(), m.begin() + k, true);
        std::vector<int> perm_pool;
        do {
            chosen.clear();
            for (int i = 0; i < n; ++i) if (m[i]) chosen.push_back(i);

            // Ancrer la rotation sur le plus petit indice, puis permuter le reste
            perm_pool.assign(chosen.begin() + 1, chosen.end());
            std::sort(perm_pool.begin(), perm_pool.end());
            do {
                std::vector<int> cyc;
                cyc.reserve(k);
                cyc.push_back(chosen.front());
                cyc.insert(cyc.end(), perm_pool.begin(), perm_pool.end());
                if (cycle_is_connected(cyc)) out.push_back(std::move(cyc));
            } while (std::next_permutation(perm_pool.begin(), perm_pool.end()));
        } while (std::prev_permutation(m.begin(), m.end()));
        return out;
    }

    // Deviation brute d'un cycle : produit des taux, ramene en bps.
    [[nodiscard]] std::optional<std::pair<std::vector<Leg>, double>>
    evaluate(const std::vector<int>& cycle) const {
        std::vector<Leg> legs;
        legs.reserve(cycle.size());
        double product = 1.0;
        for (std::size_t i = 0; i < cycle.size(); ++i) {
            const auto leg = resolve(cycle[i], cycle[(i + 1) % cycle.size()]);
            if (!leg) return std::nullopt;
            product *= leg->rate;
            legs.push_back(*leg);
        }
        return std::make_pair(std::move(legs), (product - 1.0) * 10'000.0);
    }

    // Balayage complet. Ne retourne QUE des opportunites nettes de frais.
    // evaluate() travaille sur bid/ask : la base par defaut est donc Executable.
    // Passer Mid ici serait incoherent avec le calcul du brut et ferait compter
    // le spread deux fois.
    [[nodiscard]] std::vector<Opportunity> scan(const CostModel& cost,
                                                double notional,
                                                int min_legs = 3,
                                                int max_legs = 5,
                                                bool only_profitable = true,
                                                DeviationBasis basis = DeviationBasis::Executable) const {
        std::vector<Opportunity> out;
        for (int k = min_legs; k <= max_legs; ++k) {
            for (const auto& cyc : enumerate_cycles(k)) {
                auto ev = evaluate(cyc);
                if (!ev) continue;
                auto& [legs, gross] = *ev;

                double cost_bps = 0.0;
                for (const auto& l : legs) {
                    const double sp = (basis == DeviationBasis::Mid) ? spread_of(l) : 0.0;
                    cost_bps += cost.leg_cost_bps(notional, sp);
                }

                Opportunity o;
                o.gross_bps = gross;
                o.cost_bps  = cost_bps;
                o.net_bps   = gross - cost_bps;
                o.notional  = notional;
                o.legs      = std::move(legs);
                if (!only_profitable || o.profitable()) out.push_back(std::move(o));
            }
        }
        std::sort(out.begin(), out.end(),
                  [](const Opportunity& a, const Opportunity& b) { return a.net_bps > b.net_bps; });
        return out;
    }

    [[nodiscard]] const std::vector<std::string>& currencies() const noexcept { return names_; }

private:
    struct PairKey {
        int a, b;
        bool operator==(const PairKey& o) const noexcept { return a == o.a && b == o.b; }
    };
    struct PairKeyHash {
        std::size_t operator()(const PairKey& k) const noexcept {
            return std::hash<std::int64_t>{}((std::int64_t(k.a) << 32) ^ std::uint32_t(k.b));
        }
    };

    int intern(const std::string& c) {
        if (const auto it = ids_.find(c); it != ids_.end()) return it->second;
        const int id = static_cast<int>(names_.size());
        ids_.emplace(c, id);
        names_.push_back(c);
        return id;
    }
    [[nodiscard]] std::optional<int> index_of(const std::string& c) const {
        const auto it = ids_.find(c);
        return it == ids_.end() ? std::nullopt : std::optional<int>{it->second};
    }
    [[nodiscard]] bool cycle_is_connected(const std::vector<int>& cyc) const {
        for (std::size_t i = 0; i < cyc.size(); ++i)
            if (!resolve(cyc[i], cyc[(i + 1) % cyc.size()])) return false;
        return true;
    }
    [[nodiscard]] double spread_of(const Leg& l) const {
        for (const auto& [k, q] : quotes_) {
            const std::string label = q.base + "/" + q.quote;
            if (label == l.pair) return q.spread_bps();
        }
        return 0.0;
    }

    std::unordered_map<std::string, int> ids_;
    std::vector<std::string> names_;
    std::unordered_map<PairKey, PairQuote, PairKeyHash> quotes_;
};

} // namespace kairos::arb
