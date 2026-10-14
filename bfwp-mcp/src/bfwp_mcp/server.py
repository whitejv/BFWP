"""stdio MCP server. Status, readings, events, cycles, flow, zone signatures, decay, coverage, and health."""

from mcp.server.mcpserver import MCPServer

from bfwp_mcp.compare import compare_zone_signatures as query_compare_zone_signatures
from bfwp_mcp.coverage import get_data_coverage as query_data_coverage
from bfwp_mcp.cycles import get_pump_cycles as query_pump_cycles
from bfwp_mcp.decay import get_overnight_decay as query_overnight_decay
from bfwp_mcp.events import get_events as query_events
from bfwp_mcp.flow import get_flow_totals as query_flow_totals
from bfwp_mcp.health import get_device_health as query_device_health
from bfwp_mcp.readings import get_readings as query_readings
from bfwp_mcp.signature import get_zone_signature as query_zone_signature
from bfwp_mcp.status import get_device_status as query_device_status
from bfwp_mcp.sync import sync_zone_runs as query_sync_zone_runs
from bfwp_mcp.unscheduled import get_unscheduled_pump_runs as query_unscheduled_pump_runs

mcp = MCPServer("bfwp")


@mcp.tool(name="get_pump_cycles")
def get_pump_cycles(start: str, end: str, dev: str = "", source: str = "real") -> dict:
    """Pump cycles in the range, the zone runs that overlap each cycle, and gallons per zone.

    start and end are ISO-8601. A time with no offset is America/Chicago.
    source is "sim" (well-sim.db) or "real" (well.db). dev defaults to twin1 or well1.
    """
    return query_pump_cycles(start, end, dev=dev, source=source)


@mcp.tool(name="get_unscheduled_pump_runs")
def get_unscheduled_pump_runs(start: str, end: str, dev: str = "", source: str = "real") -> dict:
    """Pump cycles and metered flow in the range that do not overlap a zone run.

    start and end are ISO-8601. A time with no offset is America/Chicago.
    source is "sim" (well-sim.db) or "real" (well.db). dev defaults to twin1 or well1.
    """
    return query_unscheduled_pump_runs(start, end, dev=dev, source=source)


@mcp.tool(name="get_overnight_decay")
def get_overnight_decay(
    date: str,
    window: str = "00:00-05:00",
    dev: str = "",
    source: str = "real",
) -> dict:
    """Overnight pressure change, the rate from first to last reading, gallons metered, and pump cycles.

    date is YYYY-MM-DD. window is HH:MM-HH:MM with no offset, read as America/Chicago.
    source is "sim" (well-sim.db) or "real" (well.db). dev defaults to twin1 or well1.
    """
    return query_overnight_decay(date, window=window, dev=dev, source=source)


@mcp.tool(name="get_data_coverage")
def get_data_coverage(start: str, end: str, dev: str = "", source: str = "real") -> dict:
    """Time spans with and without readings, and missing sequence numbers.

    A gap is longer than 3 seconds between active readings, or 90 seconds otherwise.
    start and end are ISO-8601. A time with no offset is America/Chicago.
    source is "sim" (well-sim.db) or "real" (well.db). dev defaults to twin1 or well1.
    """
    return query_data_coverage(start, end, dev=dev, source=source)


@mcp.tool(name="get_device_health")
def get_device_health(start: str, end: str, dev: str = "", source: str = "real") -> dict:
    """Health reports in the range: reset reason, uptime, RSSI, memory, and enclosure temperature.

    Reports with uptime zero are also returned as reboots.
    start and end are ISO-8601. A time with no offset is America/Chicago.
    source is "sim" (well-sim.db) or "real" (well.db). dev defaults to twin1 or well1.
    """
    return query_device_health(start, end, dev=dev, source=source)


@mcp.tool(name="get_device_status")
def get_device_status(dev: str = "", source: str = "real") -> dict:
    """Online or offline, last message time, firmware, latest health, and sequence gaps in the last 24 hours.

    source is "sim" (well-sim.db) or "real" (well.db). dev defaults to twin1 or well1.
    """
    return query_device_status(dev=dev, source=source)


@mcp.tool(name="get_readings")
def get_readings(
    start: str,
    end: str,
    resolution: str = "auto",
    fields: list[str] | None = None,
    dev: str = "",
    source: str = "real",
) -> dict:
    """Pressure, current, flow, and pump for the range.

    resolution "auto" uses raw readings up to six hours and about 2,000 points,
    then the one-minute rollup or a coarser bucket. fields defaults to psi, amps, gpm, and pump.
    start and end are ISO-8601. A time with no offset is America/Chicago.
    source is "sim" (well-sim.db) or "real" (well.db). dev defaults to twin1 or well1.
    """
    return query_readings(start, end, resolution=resolution, fields=fields, dev=dev, source=source)


@mcp.tool(name="get_events")
def get_events(
    start: str,
    end: str,
    types: list[str] | None = None,
    dev: str = "",
    source: str = "real",
) -> dict:
    """Device events in the range. `types` limits which events are returned.

    `counts` covers every match. A list longer than about 2,000 events keeps the latest ones.
    start and end are ISO-8601. A time with no offset is America/Chicago.
    source is "sim" (well-sim.db) or "real" (well.db). dev defaults to twin1 or well1.
    """
    return query_events(start, end, types=types, dev=dev, source=source)


@mcp.tool(name="get_flow_totals")
def get_flow_totals(
    start: str,
    end: str,
    bucket: str = "day",
    dev: str = "",
    source: str = "real",
) -> dict:
    """Gallons per local day, split into scheduled zone runs and unscheduled flow.

    start and end are ISO-8601. A time with no offset is America/Chicago.
    source is "sim" (well-sim.db) or "real" (well.db). dev defaults to twin1 or well1.
    """
    return query_flow_totals(start, end, bucket=bucket, dev=dev, source=source)


@mcp.tool(name="get_zone_signature")
def get_zone_signature(
    zone: str,
    start: str,
    end: str,
    dev: str = "",
    source: str = "real",
) -> dict:
    """Steady psi, amps, and gpm for each run of a zone, after skipping the first 30 seconds, plus gallons.

    The baseline is the median of those runs. Each delta is the run minus that median.
    start and end are ISO-8601. A time with no offset is America/Chicago.
    source is "sim" (well-sim.db) or "real" (well.db). dev defaults to twin1 or well1.
    """
    return query_zone_signature(zone, start, end, dev=dev, source=source)


@mcp.tool(name="compare_zone_signatures")
def compare_zone_signatures(
    start: str,
    end: str,
    dev: str = "",
    source: str = "real",
) -> dict:
    """Latest run of every zone against the median of that zone's runs in the range.

    The median matches get_zone_signature. A zone with one run has deltas of zero.
    start and end are ISO-8601. A time with no offset is America/Chicago.
    source is "sim" (well-sim.db) or "real" (well.db). dev defaults to twin1 or well1.
    """
    return query_compare_zone_signatures(start, end, dev=dev, source=source)


@mcp.tool(name="sync_zone_runs")
def sync_zone_runs(
    start: str,
    end: str,
    source: str = "real",
) -> dict:
    """Ask ingest to sync Hydrawise zone runs for the range, and return the counts.

    This server does not open the database. The Hydrawise HTTP call is not built yet,
    so the counts are zero until that check exists.
    start and end are ISO-8601. A time with no offset is America/Chicago.
    source is "sim" (well-sim.db, scenario zone rows) or "real" (well.db).
    """
    return query_sync_zone_runs(start, end, source=source)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
