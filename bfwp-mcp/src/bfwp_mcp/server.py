"""stdio MCP server for the well monitor. Status, readings, events, cycles, flow, decay, coverage, and health."""

from mcp.server.mcpserver import MCPServer

from bfwp_mcp.coverage import get_data_coverage as query_data_coverage
from bfwp_mcp.cycles import get_pump_cycles as query_pump_cycles
from bfwp_mcp.decay import get_overnight_decay as query_overnight_decay
from bfwp_mcp.events import get_events as query_events
from bfwp_mcp.flow import get_flow_totals as query_flow_totals
from bfwp_mcp.health import get_device_health as query_device_health
from bfwp_mcp.readings import get_readings as query_readings
from bfwp_mcp.status import get_device_status as query_device_status

mcp = MCPServer("bfwp")


@mcp.tool(name="get_pump_cycles")
def get_pump_cycles(start: str, end: str, dev: str = "", source: str = "real") -> dict:
    """Pump cycles in the range: start, duration, gallons, and pressure and current stats.

    start and end are ISO-8601. A time with no offset is America/Chicago.
    source is "sim" (well-sim.db) or "real" (well.db). dev defaults to twin1 or well1.
    """
    return query_pump_cycles(start, end, dev=dev, source=source)


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
    """Gallons per local day from the well meter.

    start and end are ISO-8601. A time with no offset is America/Chicago.
    source is "sim" (well-sim.db) or "real" (well.db). dev defaults to twin1 or well1.
    """
    return query_flow_totals(start, end, bucket=bucket, dev=dev, source=source)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
