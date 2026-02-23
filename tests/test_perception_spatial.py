from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PERCEPTION_SRC = ROOT / "services" / "perception" / "src"
if str(PERCEPTION_SRC) not in sys.path:
    sys.path.insert(0, str(PERCEPTION_SRC))

from nztbdo_perception.spatial import EnemyPoint, compute_spatial_features


def test_spatial_counts_front_and_near() -> None:
    features = compute_spatial_features(
        player_x=0.0,
        player_y=0.0,
        heading_deg=0.0,
        enemies=[
            EnemyPoint(5.0, 0.0),   # front + near
            EnemyPoint(3.0, 3.0),   # front cone edge
            EnemyPoint(-4.0, 0.0),  # back near
        ],
        near_radius_m=8.0,
        front_cone_angle_deg=90.0,
        front_cone_range_m=7.0,
    )
    assert features.enemies_total_near == 3
    assert features.enemies_in_front == 2
    assert features.nearest_enemy_dist is not None
