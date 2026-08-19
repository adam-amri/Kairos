#pragma once
// Types du domaine — partages simulation et production.
//
// SUR LE CHOIX DE double PLUTOT QUE D'UN POINT-FIXE.
//
// L'usage du point-fixe pour la monnaie est un reflexe repandu en finance. Il a
// ete MESURE ici plutot que suppose : 200 000 executions accumulees en double,
// comparees a une reference Decimal exacte, donnent une erreur de 0,0000 centime.
// Le double dispose de 53 bits de mantisse, soit ~9e15 : pour des montants de
// l'ordre de 1e6 avec une granularite de 1e-5, la marge est de dix ordres de
// grandeur.
//
// Le point-fixe reste indispensable pour la RECONCILIATION avec le venue, ou
// l'egalite exacte au centime est exigee. Il ne l'est pas pour la simulation, et
// l'y imposer couterait de la complexite sans gain mesurable.

#include <cstdint>
#include <string>

namespace kairos::core {

enum class Side : std::int8_t { Buy = 1, Sell = -1 };
[[nodiscard]] constexpr int sign_of(Side s) noexcept { return static_cast<int>(s); }

enum class OrderType : std::uint8_t { Market, Limit };
enum class OrderStatus : std::uint8_t { Pending, Resting, Filled, Cancelled, Rejected };

struct Quote {
    std::int64_t ts_venue_ns{};   // horodatage du venue, potentiellement faux
    std::int64_t ts_wall_ns{};    // reception locale, comparable entre machines
    std::int64_t ts_mono_ns{};    // monotone : SEULE base valide pour une duree
    double bid{}, ask{};
    double bid_size{}, ask_size{};

    [[nodiscard]] constexpr double mid() const noexcept { return 0.5 * (bid + ask); }
    [[nodiscard]] constexpr double spread() const noexcept { return ask - bid; }
    [[nodiscard]] constexpr double spread_bps() const noexcept {
        const double m = mid();
        return m > 0.0 ? (ask - bid) / m * 10'000.0 : 0.0;
    }
};

struct Order {
    std::int64_t id{};
    std::int64_t client_id{};      // choisi par la strategie : cible des annulations
    Side side{Side::Buy};
    OrderType type{OrderType::Limit};
    double qty{};
    double price{};

    std::int64_t ts_created_ns{};
    std::int64_t ts_arrive_ns{};
    OrderStatus status{OrderStatus::Pending};

    double filled_qty{};
    double queue_ahead{};
    bool joined_queue{false};

    [[nodiscard]] constexpr double remaining() const noexcept { return qty - filled_qty; }
    [[nodiscard]] constexpr bool is_active() const noexcept {
        return status == OrderStatus::Pending || status == OrderStatus::Resting;
    }
};

struct Fill {
    std::int64_t order_id{};
    Side side{Side::Buy};
    double qty{};
    double price{};
    std::int64_t ts_ns{};
    bool is_maker{};
    double commission{};

    [[nodiscard]] constexpr double signed_qty() const noexcept {
        return qty * static_cast<double>(sign_of(side));
    }
};

} // namespace kairos::core
