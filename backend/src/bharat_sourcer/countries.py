"""Countries we source for: one registry for the facts that differ between countries.

Only India is supported today. Code that needs a country fact (currency, mains, sellers,
map area, market cities) reads it from here rather than hard-coding India, so adding a
country starts with a `Country` entry. The full checklist for a new country (seller
search adapters, shipping policies, tax rules, prompts, safety text) is in
docs/contracts/countries.md.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    """A market city: nearby-market lookups by city use its centre (approximate)."""

    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Country:
    code: str  # ISO 3166-1 alpha-2
    name: str
    currency: str  # ISO 4217; prices are stored in this currency
    locale: str  # BCP 47, for number and date formatting
    mains_vac: float
    mains_hz: int
    plug_types: tuple[str, ...]
    tax_name: str
    # Domain suffix of local shops, used to rank grounded search results.
    local_tld: str
    # Curated sellers that ship within the country; ranking only, never trust.
    seller_domains: frozenset[str]
    # Bounding box for coordinates (lat, lng ranges); a coarse inside-the-country check.
    lat_range: tuple[float, float]
    lng_range: tuple[float, float]
    cities: tuple[City, ...]

    def contains(self, lat: float, lng: float) -> bool:
        return (
            self.lat_range[0] <= lat <= self.lat_range[1]
            and self.lng_range[0] <= lng <= self.lng_range[1]
        )

    def city(self, name: str) -> City | None:
        key = name.strip().casefold()
        return next((city for city in self.cities if city.name.casefold() == key), None)


INDIA = Country(
    code="IN",
    name="India",
    currency="INR",
    locale="en-IN",
    mains_vac=230,
    mains_hz=50,
    plug_types=("C", "D", "M"),
    tax_name="GST",
    local_tld=".in",
    seller_domains=frozenset(
        {
            "robu.in",
            "robocraze.com",
            "quartzcomponents.com",
            "evelta.com",
            "electronicscomp.com",
            "flyrobo.in",
            "rytronics.in",
            "compoindia.com",
            "sharvielectronics.com",
            "probots.co.in",
            "thingbits.in",
            "hubtronics.in",
            "sunrobotics.in",
            "zbotic.in",
            "campuscomponent.com",
            "roboelements.com",
            "ktron.in",
            "amazon.in",
            "flipkart.com",
            "in.element14.com",
        }
    ),
    lat_range=(6.0, 37.6),
    lng_range=(68.0, 97.5),
    cities=(
        City("Ahmedabad", 23.0225, 72.5714),
        City("Bengaluru", 12.9716, 77.5946),
        City("Chandigarh", 30.7333, 76.7794),
        City("Chennai", 13.0827, 80.2707),
        City("Coimbatore", 11.0168, 76.9558),
        City("Delhi", 28.6139, 77.2090),
        City("Gurugram", 28.4595, 77.0266),
        City("Hyderabad", 17.3850, 78.4867),
        City("Indore", 22.7196, 75.8577),
        City("Jaipur", 26.9124, 75.7873),
        City("Kochi", 9.9312, 76.2673),
        City("Kolkata", 22.5726, 88.3639),
        City("Lucknow", 26.8467, 80.9462),
        City("Mumbai", 19.0760, 72.8777),
        City("Nagpur", 21.1458, 79.0882),
        City("Pune", 18.5204, 73.8567),
        City("Surat", 21.1702, 72.8311),
        City("Thiruvananthapuram", 8.5241, 76.9366),
        City("Visakhapatnam", 17.6868, 83.2185),
    ),
)

COUNTRIES: dict[str, Country] = {INDIA.code: INDIA}
DEFAULT_COUNTRY = INDIA.code


def country(code: str | None) -> Country:
    """The registry entry for a supported code; unknown or missing codes get the default."""
    return COUNTRIES.get(code or DEFAULT_COUNTRY, COUNTRIES[DEFAULT_COUNTRY])
