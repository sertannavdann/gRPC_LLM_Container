"""
Mock Navigation Adapter - Development/Testing

Generates realistic mock navigation/route data for UI development.
Simulates data from Google Maps, Waze, Apple Maps, etc.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List
import random
import uuid

from ..base import BaseAdapter, AdapterConfig
from ..registry import register_adapter
from ...schemas.canonical import (
    NavigationRoute,
    GeoPoint,
    TrafficLevel,
    TransportMode,
)


# Configuration constant: default mock locations used for route generation
MOCK_LOCATION_DATA = {
    "home": GeoPoint(43.6532, -79.3832, "123 Home Street, Toronto, ON"),
    "office": GeoPoint(43.6510, -79.3470, "456 King St W, Toronto, ON"),
    "gym": GeoPoint(43.6480, -79.3920, "789 Queen St W, Toronto, ON"),
    "grocery": GeoPoint(43.6650, -79.3850, "321 Bloor St W, Toronto, ON"),
    "cafe": GeoPoint(43.6490, -79.3970, "Coffee House, Ossington Ave, Toronto"),
    "airport": GeoPoint(43.6777, -79.6248, "Toronto Pearson Airport"),
    "downtown": GeoPoint(43.6426, -79.3871, "Union Station, Toronto"),
}


@register_adapter(
    category="navigation",
    platform="mock",
    display_name="Mock Maps",
    description="Development mock adapter with realistic navigation data",
    icon="🗺️",
    requires_auth=False,
)
class MockNavigationAdapter(BaseAdapter[NavigationRoute]):
    """
    Mock navigation adapter for development and testing.
    Generates realistic route data.
    """
    
    category = "navigation"
    platform = "mock"
    
    def __init__(self, config: AdapterConfig = None):
        super().__init__(config)
        self._seed = random.randint(1, 10000)
    
    def _generate_route(
        self,
        origin: GeoPoint,
        destination: GeoPoint,
        mode: TransportMode = TransportMode.DRIVING,
    ) -> Dict[str, Any]:
        """Generate a realistic route between two points."""
        # Calculate approximate distance (simple Haversine-like approximation)
        lat_diff = abs(origin.latitude - destination.latitude)
        lon_diff = abs(origin.longitude - destination.longitude)
        distance_km = ((lat_diff ** 2 + lon_diff ** 2) ** 0.5) * 111  # ~111km per degree
        distance_meters = distance_km * 1000
        
        # Calculate duration based on mode
        speed_map = {
            TransportMode.DRIVING: 35,  # km/h average in city
            TransportMode.WALKING: 5,
            TransportMode.CYCLING: 15,
            TransportMode.TRANSIT: 25,
        }
        speed = speed_map.get(mode, 30)
        duration_hours = distance_km / speed
        duration_seconds = int(duration_hours * 3600)
        
        # Apply traffic factor
        traffic_level = random.choice([
            TrafficLevel.LIGHT,
            TrafficLevel.MODERATE,
            TrafficLevel.MODERATE,
            TrafficLevel.HEAVY,
        ])
        traffic_multiplier = {
            TrafficLevel.LIGHT: 1.0,
            TrafficLevel.MODERATE: 1.2,
            TrafficLevel.HEAVY: 1.5,
            TrafficLevel.BLOCKED: 2.0,
        }
        duration_seconds = int(duration_seconds * traffic_multiplier[traffic_level])
        
        eta = datetime.now() + timedelta(seconds=duration_seconds)
        
        return {
            "id": f"route_{uuid.uuid4().hex[:8]}",
            "origin": {
                "lat": origin.latitude,
                "lng": origin.longitude,
                "address": origin.address,
            },
            "destination": {
                "lat": destination.latitude,
                "lng": destination.longitude,
                "address": destination.address,
            },
            "distance_meters": round(distance_meters),
            "duration_seconds": duration_seconds,
            "traffic_level": traffic_level.value,
            "eta": eta.isoformat(),
            "mode": mode.value,
        }
    
    async def fetch_raw(self, config: AdapterConfig) -> Dict[str, Any]:
        """Generate mock raw data simulating API response."""
        random.seed(self._seed)
        
        # Get origin/destination from config or use defaults
        settings = config.settings if config else {}
        
        origin_name = settings.get("origin", "home")
        destination_name = settings.get("destination", "office")
        
        origin = MOCK_LOCATION_DATA.get(origin_name, MOCK_LOCATION_DATA["home"])
        destination = MOCK_LOCATION_DATA.get(destination_name, MOCK_LOCATION_DATA["office"])
        
        # Generate primary route
        primary_route = self._generate_route(origin, destination)
        
        # Generate alternative routes
        alternatives = []
        for i in range(2):
            alt_route = self._generate_route(origin, destination)
            # Make alternatives slightly different
            alt_route["duration_seconds"] = int(
                alt_route["duration_seconds"] * random.uniform(0.9, 1.3)
            )
            alt_route["id"] = f"alt_route_{i}_{uuid.uuid4().hex[:4]}"
            alternatives.append(alt_route)
        
        # Generate commute suggestions
        commute = {
            "home_to_work": self._generate_route(
                MOCK_LOCATION_DATA["home"],
                MOCK_LOCATION_DATA["office"],
            ),
            "work_to_home": self._generate_route(
                MOCK_LOCATION_DATA["office"],
                MOCK_LOCATION_DATA["home"],
            ),
        }
        
        return {
            "route": primary_route,
            "alternatives": alternatives,
            "commute": commute,
            "saved_locations": {
                name: {"lat": loc.latitude, "lng": loc.longitude, "address": loc.address}
                for name, loc in MOCK_LOCATION_DATA.items()
            },
            "mock": True,
        }
    
    def transform(self, raw_data: Dict[str, Any]) -> List[NavigationRoute]:
        """Transform mock data to canonical format."""
        routes = []
        
        # Primary route
        if "route" in raw_data:
            routes.append(self._transform_route(raw_data["route"]))
        
        # Alternative routes (stored in primary route's alternatives)
        if routes and "alternatives" in raw_data:
            for alt in raw_data["alternatives"]:
                alt_route = self._transform_route(alt)
                routes[0].alternative_routes.append(alt_route)
        
        return routes
    
    def _transform_route(self, route_data: Dict[str, Any]) -> NavigationRoute:
        """Transform a single route to canonical format."""
        origin = GeoPoint(
            latitude=route_data["origin"]["lat"],
            longitude=route_data["origin"]["lng"],
            address=route_data["origin"].get("address"),
        )
        
        destination = GeoPoint(
            latitude=route_data["destination"]["lat"],
            longitude=route_data["destination"]["lng"],
            address=route_data["destination"].get("address"),
        )
        
        traffic_level = TrafficLevel(route_data.get("traffic_level", "unknown"))
        transport_mode = TransportMode(route_data.get("mode", "driving"))
        
        eta = None
        if route_data.get("eta"):
            eta = datetime.fromisoformat(route_data["eta"])
        
        return NavigationRoute(
            id=f"mock:{route_data['id']}",
            origin=origin,
            destination=destination,
            distance_meters=route_data["distance_meters"],
            duration_seconds=route_data["duration_seconds"],
            traffic_level=traffic_level,
            estimated_arrival=eta,
            transport_mode=transport_mode,
            platform=self.platform,
            metadata={"raw": route_data}
        )
    
    def get_commute(self, raw_data: Dict[str, Any]) -> Dict[str, NavigationRoute]:
        """Get commute routes (home↔work)."""
        commute_data = raw_data.get("commute", {})
        return {
            "home_to_work": self._transform_route(commute_data["home_to_work"]),
            "work_to_home": self._transform_route(commute_data["work_to_home"]),
        }
    
    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "read": True,
            "write": False,
            "real_time": True,  # Traffic updates
            "batch": True,
            "webhooks": False,
            "directions": True,
            "traffic": True,
            "eta": True,
            "alternatives": True,
        }
