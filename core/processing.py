import logging
import math

from sgp4.api import Satrec
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import ProcessedTle, TleRecord

logger = logging.getLogger(__name__)

EARTH_MU = 398600.4418  # km³/s²
EARTH_RADIUS_KM = 6371.0


def compute_orbital_params(tle_line1: str, tle_line2: str) -> dict:
    """Parse TLE lines and compute orbital parameters using sgp4.

    Returns a dict with keys: period_minutes, apogee_km, perigee_km,
    inclination_deg, eccentricity, mean_motion_rev_per_day.
    """
    sat = Satrec.twoline2rv(tle_line1, tle_line2)

    # sat.no_kozai is in rad/min; convert to rev/day
    mean_motion_rev_per_day = sat.no_kozai * 1440.0 / (2.0 * math.pi)
    period_minutes = 1440.0 / mean_motion_rev_per_day

    # Semi-major axis: a = (μ / n²)^(1/3), n in rad/s
    n_rad_per_sec = sat.no_kozai / 60.0
    a_km = (EARTH_MU / (n_rad_per_sec**2)) ** (1.0 / 3.0)

    eccentricity = sat.ecco
    apogee_km = a_km * (1.0 + eccentricity) - EARTH_RADIUS_KM
    perigee_km = a_km * (1.0 - eccentricity) - EARTH_RADIUS_KM

    # sat.inclo is in radians
    inclination_deg = math.degrees(sat.inclo)

    return {
        "period_minutes": period_minutes,
        "apogee_km": apogee_km,
        "perigee_km": perigee_km,
        "inclination_deg": inclination_deg,
        "eccentricity": eccentricity,
        "mean_motion_rev_per_day": mean_motion_rev_per_day,
    }


def classify_orbit(apogee_km: float, perigee_km: float, eccentricity: float) -> str:
    """Classify orbit type based on altitude and eccentricity."""
    if eccentricity > 0.25:
        return "HEO"
    if 35_586 <= apogee_km <= 35_986 and eccentricity <= 0.25:
        return "GEO"
    if perigee_km < 2_000 and eccentricity <= 0.25:
        return "LEO"
    if 2_000 <= perigee_km < 35_586:
        return "MEO"
    return "OTHER"


def process_unprocessed(session: Session) -> dict:
    """Compute orbital parameters for all TleRecord rows that have no ProcessedTle row.

    Returns {"processed": n, "errors": n}.
    """
    stmt = (
        select(TleRecord)
        .outerjoin(TleRecord.processed)
        .where(ProcessedTle.id.is_(None))
    )
    records = session.execute(stmt).scalars().all()

    processed = 0
    errors = 0

    for record in records:
        try:
            params = compute_orbital_params(record.tle_line1, record.tle_line2)
            orbit_type = classify_orbit(
                params["apogee_km"], params["perigee_km"], params["eccentricity"]
            )
            session.add(
                ProcessedTle(
                    tle_record_id=record.id,
                    orbit_type=orbit_type,
                    **params,
                )
            )
            processed += 1
        except Exception as exc:
            logger.error(
                "Failed to process TLE record",
                extra={"tle_record_id": record.id, "error": str(exc)},
            )
            errors += 1

    session.flush()
    logger.info("process complete", extra={"processed": processed, "errors": errors})
    return {"processed": processed, "errors": errors}
