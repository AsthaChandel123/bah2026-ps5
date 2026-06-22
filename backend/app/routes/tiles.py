"""Map-tile endpoint — documented stub.

Per ARCHITECTURE.md S7/S11 the production map tiles are served as **PMTiles**
byte-ranges from Cloudflare R2 (raster pyramids, 1-2 cached range GETs) or
rendered dynamically by **TiTiler** over COGs for the long tail / what-if
layers. Neither belongs in this lightweight in-memory FastAPI service, so this
endpoint is intentionally a stub that returns HTTP 501 with a pointer to the
real serving path. The frontend renders fields client-side from the JSON cube
(ARCHITECTURE S9.1), so it does not depend on this endpoint for the PoC.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

router = APIRouter(tags=["tiles"])


@router.get(
    "/api/tiles/{z}/{x}/{y}.png",
    summary="Map raster tile (stub — served by PMTiles/TiTiler in production)",
    responses={501: {"description": "Not implemented in the PoC API service"}},
)
def get_tile(z: int, x: int, y: int) -> Response:
    """Return 501 with guidance. Tiles are a static R2/PMTiles concern.

    In production, MapLibre fetches ``(z,x,y)`` directly from a PMTiles archive
    on R2 via the PMTiles protocol (Hilbert tile id -> byte range), or from a
    TiTiler endpoint for dynamic colormap / date / what-if tiles. See
    ``backend/edge/worker.js`` for the edge serving design.
    """
    body = (
        f'{{"error":"not_implemented",'
        f'"tile":{{"z":{z},"x":{x},"y":{y}}},'
        f'"detail":"Map tiles are served by PMTiles byte-ranges from Cloudflare '
        f'R2 (stable layers) or TiTiler over COGs (dynamic/what-if layers) per '
        f'ARCHITECTURE S7/S11. The dashboard renders fields client-side from the '
        f'JSON cube and does not require this endpoint for the PoC."}}'
    )
    return Response(content=body, media_type="application/json", status_code=501)
