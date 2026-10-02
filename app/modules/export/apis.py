from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.modules.accounts.models import User
from app.modules.export.schemas import ExportPreviewResponse, ExportRequest
from app.modules.export.service import ExportService


async def export_preview_endpoint(
    payload: ExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ExportPreviewResponse:
    """Preview record counts and resolved date range for export criteria (Admin Only)."""
    try:
        start_dt, end_dt, date_label = ExportService.parse_date_range(
            payload.date_range, payload.start_date, payload.end_date
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    counts = {}
    total = 0
    for cat in payload.categories:
        c = cat.lower().strip()
        cnt = ExportService.get_category_count(db, c, start_dt, end_dt, payload.filters)
        counts[c] = cnt
        total += cnt

    return ExportPreviewResponse(
        counts=counts,
        total_records=total,
        date_range_label=date_label,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )


async def export_download_endpoint(
    payload: ExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Download exported CSV or ZIP archive matching criteria (Admin Only)."""
    try:
        start_dt, end_dt, date_label = ExportService.parse_date_range(
            payload.date_range, payload.start_date, payload.end_date
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Check total count first to avoid returning empty file
    total_count = sum(
        ExportService.get_category_count(db, cat.lower().strip(), start_dt, end_dt, payload.filters)
        for cat in payload.categories
    )

    if total_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No records match the selected export criteria.",
        )

    try:
        content_bytes, media_type, filename = ExportService.generate_export_payload(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Access-Control-Expose-Headers": "Content-Disposition",
    }

    return StreamingResponse(
        iter([content_bytes]),
        media_type=media_type,
        headers=headers,
    )
