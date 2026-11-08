"""
geometry_utils.py
Dedicated geometry and table reconstruction utility for layout extraction.
Provides robust outer hull expansion, cell clustering, and bounding box filtering
to prevent sub-cell slicing, text-line clipping, and full-page canvas over-capture.
"""

import logging
from typing import List, Tuple
import numpy as np

logger = logging.getLogger("GeometryUtils")

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False


class GeometryUtils:

    @staticmethod
    def merge_overlapping_boxes(
        boxes: List[Tuple[int, int, int, int]], threshold: int = 25
    ) -> List[Tuple[int, int, int, int]]:
        """Merges overlapping or tightly adjacent bounding boxes into unified hulls."""
        if not boxes:
            return []

        current = sorted(boxes, key=lambda b: (b[1], b[0]))
        changed = True
        while changed:
            changed = False
            merged: List[Tuple[int, int, int, int]] = []
            for box in current:
                if merged and GeometryUtils._boxes_overlap(merged[-1], box, threshold):
                    merged[-1] = GeometryUtils._union_boxes(merged[-1], box)
                    changed = True
                else:
                    merged.append(box)
            current = merged

        return current

    @staticmethod
    def _boxes_overlap(
        a: Tuple[int, int, int, int], b: Tuple[int, int, int, int], threshold: int
    ) -> bool:
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b
        return (
            bx0 <= ax1 + threshold and bx1 >= ax0 - threshold
            and by0 <= ay1 + threshold and by1 >= ay0 - threshold
        )

    @staticmethod
    def _union_boxes(
        a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]
    ) -> Tuple[int, int, int, int]:
        return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))

    @staticmethod
    def compute_table_outer_hull(
        cell_boxes: List[Tuple[int, int, int, int]], page_width: float, page_height: float
    ) -> List[Tuple[int, int, int, int]]:
        """
        Takes fragmented cell boxes or grid contours and computes unified outer hulls
        for tables, ensuring full header and row enclosure without sub-cell slicing.
        """
        if not cell_boxes:
            return []

        # Group boxes by vertical alignment proximity to form row/column clusters
        merged = GeometryUtils.merge_overlapping_boxes(cell_boxes, threshold=40)
        
        # Further refine into master structural hulls
        refined_hulls = []
        for box in merged:
            x0, y0, x1, y1 = box
            w = x1 - x0
            h = y1 - y0

            # Discard trivial slivers or lines
            if w < 100 or h < 50:
                continue

            # Enforce maximum area limit to prevent full-page canvas over-capture
            if (w * h) > (page_width * page_height * 0.75):
                logger.warning(f"Discarding oversized hull exceeding 75% of page canvas: {box}")
                continue

            refined_hulls.append((x0, y0, x1, y1))

        return refined_hulls
