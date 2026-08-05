"""Reading a board layout out of a photograph of the keyboard.

The point of this module is to save the tedious part of describing a board: typing two
dozen pairs of coordinates by hand. It finds the keycaps in a photo, works out the key
pitch, and hands back a set of boxes in the same key-pitch units the rest of the app uses.

It is deliberately a *starting point*, not an oracle. Photographs vary enormously in
lighting, angle and contrast, and a keyboard shot at an angle is not an orthographic
projection of itself. So everything here is written to fail softly -- to return a plausible
grid that the user then drags into place in the editor -- rather than to be right every
time. Two decisions follow from that:

* No new dependencies. A real computer-vision stack (OpenCV, numpy) would detect better,
  but it would also more than double the size of the executable to improve the first guess
  in a workflow that ends in manual correction anyway. Everything here runs on QImage and
  the standard library.
* Missing keycaps are inferred from the gaps. A board photographed with caps pulled off --
  which is exactly how the asterisk column usually looks -- leaves a hole in an otherwise
  even row. A hole an integer number of pitches wide is filled with placeholder keys, so
  the switch still gets a box in the layout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from .protocol import STENO_ORDER

# The photo is analysed at this size regardless of what came in. Detection quality is
# limited by contrast and geometry, not resolution, and the connected-component pass is a
# Python-level loop over every pixel -- so a 12-megapixel phone photo would cost minutes
# for no gain.
WORK_DIM = 480

# A keycap has to be at least this fraction of the working image to count, which throws out
# screws, silkscreen text and sensor noise, and at most this much, which throws out the
# desk, the PCB and any brightly lit background.
MIN_AREA_FRACTION = 0.0012
MAX_AREA_FRACTION = 0.05

# How square a blob has to be. Keycaps are square-ish; a 2u key or two caps merged into one
# blob comes out wider than this and is dealt with by splitting rather than rejection.
MAX_ASPECT = 1.55

# A blob has to fill this much of its own bounding box. A cap does; an L-shaped shadow or a
# run of connected background does not.
MIN_FILL = 0.55


@dataclass(frozen=True)
class Box:
    """One detected keycap, in key-pitch units relative to the top-left of the layout."""

    col: float
    row: float
    width: float = 1.0
    height: float = 1.0
    inferred: bool = False   # True when this box fills a gap rather than a detected cap

    @property
    def centre(self) -> tuple[float, float]:
        return (self.col + self.width / 2, self.row + self.height / 2)


@dataclass
class Detection:
    """What was found in a photo, plus what is needed to draw the photo behind it."""

    boxes: list[Box] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)   # Guessed steno key per box
    warnings: list[str] = field(default_factory=list)

    # Where the photo sits in key-pitch units, so the editor can draw it as a backdrop
    # that lines up with the boxes by construction rather than by eye.
    photo_col: float = 0.0
    photo_row: float = 0.0
    photo_width: float = 1.0
    photo_height: float = 1.0

    detected: int = 0    # Caps actually found, before gap filling
    filled: int = 0      # Placeholder boxes added for missing caps

    @property
    def ok(self) -> bool:
        return len(self.boxes) >= 4


# ---------------------------------------------------------------------------------------
# Image plumbing
# ---------------------------------------------------------------------------------------


def _load_grey(path: Path) -> tuple[list[int], int, int, float] | None:
    """Load an image as an 8-bit grey list, scaled down. Returns (pixels, w, h, scale).

    `scale` is how many original pixels one working pixel covers, so results can be mapped
    back onto the full-size photo.
    """
    image = QImage(str(path))
    if image.isNull():
        return None

    longest = max(image.width(), image.height())
    if longest > WORK_DIM:
        small = image.scaled(
            WORK_DIM, WORK_DIM, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
    else:
        small = image

    small = small.convertToFormat(QImage.Format_Grayscale8)
    width, height = small.width(), small.height()
    stride = small.bytesPerLine()
    raw = bytes(small.constBits())

    # Grayscale8 rows are padded to a 4-byte boundary, so the buffer is not simply w*h.
    pixels: list[int] = []
    for y in range(height):
        start = y * stride
        pixels.extend(raw[start:start + width])

    return pixels, width, height, image.width() / max(width, 1)


def _adaptive_mask(pixels: list[int], width: int, height: int) -> bytearray:
    """Threshold each pixel against the mean of its neighbourhood.

    A global threshold fails on the photos people actually take: one end of the board is
    lit and the other is in shadow, and black keycaps on a black PCB differ from their
    surroundings by only a few levels. Comparing against a local mean handles both, and
    picks out the lighter cap tops from the dark seams between them.

    The local mean comes from a summed-area table, so the window size costs nothing.
    """
    # Summed-area table with a zero row and column, so any window is four lookups.
    integral = [0] * ((width + 1) * (height + 1))
    for y in range(height):
        row_sum = 0
        base = y * width
        above = y * (width + 1)
        below = above + width + 1
        for x in range(width):
            row_sum += pixels[base + x]
            integral[below + x + 1] = integral[above + x + 1] + row_sum

    radius = max(6, min(width, height) // 14)
    bias = 3  # Levels a pixel must clear the local mean by, to reject flat noise.

    mask = bytearray(width * height)
    for y in range(height):
        y0 = max(0, y - radius)
        y1 = min(height - 1, y + radius)
        top = y0 * (width + 1)
        bottom = (y1 + 1) * (width + 1)
        span_y = y1 - y0 + 1
        base = y * width
        for x in range(width):
            x0 = max(0, x - radius)
            x1 = min(width - 1, x + radius)
            total = (
                integral[bottom + x1 + 1] - integral[bottom + x0]
                - integral[top + x1 + 1] + integral[top + x0]
            )
            mean = total / (span_y * (x1 - x0 + 1))
            if pixels[base + x] > mean + bias:
                mask[base + x] = 1
    return mask


@dataclass
class _Blob:
    min_x: int
    min_y: int
    max_x: int
    max_y: int
    area: int

    @property
    def width(self) -> int:
        return self.max_x - self.min_x + 1

    @property
    def height(self) -> int:
        return self.max_y - self.min_y + 1

    @property
    def fill(self) -> float:
        return self.area / max(1, self.width * self.height)


def _components(mask: bytearray, width: int, height: int, min_area: int) -> list[_Blob]:
    """Label 4-connected runs of set pixels. Iterative, because photos make deep stacks."""
    seen = bytearray(width * height)
    blobs: list[_Blob] = []

    for start in range(width * height):
        if not mask[start] or seen[start]:
            continue
        seen[start] = 1
        stack = [start]
        min_x = max_x = start % width
        min_y = max_y = start // width
        area = 0

        while stack:
            index = stack.pop()
            area += 1
            x, y = index % width, index // width
            if x < min_x:
                min_x = x
            elif x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            elif y > max_y:
                max_y = y

            if x > 0 and mask[index - 1] and not seen[index - 1]:
                seen[index - 1] = 1
                stack.append(index - 1)
            if x + 1 < width and mask[index + 1] and not seen[index + 1]:
                seen[index + 1] = 1
                stack.append(index + 1)
            if y > 0 and mask[index - width] and not seen[index - width]:
                seen[index - width] = 1
                stack.append(index - width)
            if y + 1 < height and mask[index + width] and not seen[index + width]:
                seen[index + width] = 1
                stack.append(index + width)

        if area >= min_area:
            blobs.append(_Blob(min_x, min_y, max_x, max_y, area))

    return blobs


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _split_merged(blobs: list[_Blob], unit: float) -> list[_Blob]:
    """Cut blobs that swallowed their neighbours back into cap-sized pieces.

    Two caps whose shared seam catches the light merge into one wide blob. Rejecting those
    would quietly drop real keys, so instead a blob close to a whole multiple of the key
    pitch is divided into that many equal parts.
    """
    result: list[_Blob] = []
    for blob in blobs:
        across = max(1, round(blob.width / unit))
        down = max(1, round(blob.height / unit))
        if across <= 1 and down <= 1:
            result.append(blob)
            continue

        step_x = blob.width / across
        step_y = blob.height / down
        share = blob.area // (across * down)
        for i in range(across):
            for j in range(down):
                x0 = blob.min_x + round(i * step_x)
                y0 = blob.min_y + round(j * step_y)
                result.append(
                    _Blob(
                        x0, y0,
                        x0 + round(step_x) - 1,
                        y0 + round(step_y) - 1,
                        share,
                    )
                )
    return result


def _cluster_rows(items: list, key, tolerance: float) -> list[list]:
    """Group items into rows by a coordinate, splitting wherever a gap exceeds tolerance."""
    if not items:
        return []
    ordered = sorted(items, key=key)
    rows = [[ordered[0]]]
    for item in ordered[1:]:
        if key(item) - key(rows[-1][-1]) > tolerance:
            rows.append([])
        rows[-1].append(item)
    return rows


def _pitch(rows: list[list[_Blob]], fallback: float) -> float:
    """Horizontal key pitch: the typical gap between neighbouring caps within a row.

    The gap across the middle of a split board is much larger than one pitch, so the
    median of the smaller half of the gaps is used rather than the median of all of them.
    """
    gaps: list[float] = []
    for row in rows:
        ordered = sorted(row, key=lambda b: b.min_x)
        for a, b in zip(ordered, ordered[1:]):
            gap = (b.min_x + b.width / 2) - (a.min_x + a.width / 2)
            if gap > 0:
                gaps.append(gap)
    if not gaps:
        return fallback
    gaps.sort()
    lower = gaps[: max(1, len(gaps) // 2 + 1)]
    return _median(lower) or fallback


# ---------------------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------------------


def detect(path: Path) -> Detection:
    """Find the keycaps in a photo and return them as boxes in key-pitch units."""
    result = Detection()

    loaded = _load_grey(Path(path))
    if loaded is None:
        result.warnings.append("That file could not be read as an image.")
        return result
    pixels, width, height, _scale = loaded

    total = width * height
    mask = _adaptive_mask(pixels, width, height)
    blobs = _components(mask, width, height, int(total * MIN_AREA_FRACTION))

    blobs = [
        blob for blob in blobs
        if blob.area <= total * MAX_AREA_FRACTION and blob.fill >= MIN_FILL
    ]
    if len(blobs) < 4:
        result.warnings.append(
            "No keycaps could be picked out of that photo. A shot taken straight down, "
            "with the board filling the frame and even lighting, works best — or start "
            "from a built-in board and drag the keys into place."
        )
        return result

    # The typical cap height sets the scale. Height is used rather than width because rows
    # are separated by a wider gap than columns, so caps merge sideways far more often.
    unit = _median([float(blob.height) for blob in blobs])
    if unit <= 0:
        result.warnings.append("The keycaps in that photo are too small to measure.")
        return result

    blobs = _split_merged(blobs, unit)
    blobs = [
        blob for blob in blobs
        if 1 / MAX_ASPECT <= blob.width / max(1, blob.height) <= MAX_ASPECT
        and 0.45 * unit <= blob.height <= 2.6 * unit
    ]
    if len(blobs) < 4:
        result.warnings.append("Too few keycaps survived filtering to build a layout.")
        return result

    rows = _cluster_rows(blobs, lambda b: b.min_y + b.height / 2, unit * 0.62)
    pitch = _pitch(rows, unit)
    result.detected = len(blobs)

    rows, filled = _fill_row_gaps(rows, pitch)
    result.filled = filled

    # Convert to key-pitch units, with the top-left of the layout at the origin.
    min_x = min(blob.min_x for row in rows for blob, _ in row)
    min_y = min(blob.min_y for row in rows for blob, _ in row)

    def to_units(value: float) -> float:
        return round(value / pitch, 3)

    boxes: list[Box] = []
    for row in rows:
        for blob, inferred in row:
            boxes.append(
                Box(
                    col=to_units(blob.min_x - min_x),
                    row=to_units(blob.min_y - min_y),
                    width=max(0.4, to_units(blob.width)),
                    height=max(0.4, to_units(blob.height)),
                    inferred=inferred,
                )
            )

    boxes = _snap_rows(boxes)
    result.boxes = boxes
    result.keys = infer_keys(boxes)

    # Place the photo in the same coordinate space, so the backdrop lines up with the boxes.
    result.photo_col = to_units(-min_x)
    result.photo_row = to_units(-min_y)
    result.photo_width = to_units(width)
    result.photo_height = to_units(height)

    if filled:
        result.warnings.append(
            f"{filled} gap(s) in the rows were filled with a key — that is usually a "
            f"switch photographed without its keycap. Check those before saving."
        )
    return result


def _fill_row_gaps(
    rows: list[list[_Blob]], pitch: float
) -> tuple[list[list[tuple[_Blob, bool]]], int]:
    """Insert a placeholder wherever a row has a whole-pitch hole in it.

    A switch with the keycap pulled off does not read as a cap, but it does leave an
    exactly key-sized hole in an otherwise even row -- which is a stronger signal than
    anything visible in the photo, and is how the asterisk column usually looks.

    Holes are measured centre to centre, not edge to edge. Centre spacing is a whole
    multiple of the key pitch whatever the keycaps happen to measure, so the test does not
    quietly depend on how much of each cap the threshold caught.
    """
    filled = 0
    out: list[list[tuple[_Blob, bool]]] = []

    for row in rows:
        ordered = sorted(row, key=lambda blob: blob.min_x)
        cap_w = _median([float(blob.width) for blob in ordered])
        cap_h = _median([float(blob.height) for blob in ordered])
        marked: list[tuple[_Blob, bool]] = [(ordered[0], False)]

        for previous, blob in zip(ordered, ordered[1:]):
            start = previous.min_x + previous.width / 2
            end = blob.min_x + blob.width / 2
            steps = round((end - start) / pitch)
            # Two pitches between neighbouring caps means one key is unaccounted for. The
            # tolerance keeps a merely wide gap from sprouting keys that do not exist.
            if steps >= 2 and abs((end - start) / pitch - steps) < 0.3:
                step = (end - start) / steps
                middle_y = previous.min_y + previous.height / 2
                for i in range(1, steps):
                    x0 = round(start + i * step - cap_w / 2)
                    y0 = round(middle_y - cap_h / 2)
                    marked.append((
                        _Blob(x0, y0, x0 + round(cap_w) - 1, y0 + round(cap_h) - 1, 0),
                        True,
                    ))
                    filled += 1
            marked.append((blob, False))
        out.append(marked)

    return out, filled


def _snap_rows(boxes: list[Box]) -> list[Box]:
    """Flatten each row onto a single row coordinate and a single height.

    A photo taken slightly off-square gives every cap in a row a marginally different y.
    Left alone that reads as a wobbly keyboard; worse, it makes the finger-rest derivation
    treat one row as two. Rounding to a common value per row is what the user would do
    first anyway.
    """
    if not boxes:
        return []
    rows = _cluster_rows(boxes, lambda b: b.row + b.height / 2, 0.62)
    snapped: list[Box] = []
    for row in rows:
        top = round(_median([box.row for box in row]), 2)
        height = round(_median([box.height for box in row]), 2)
        for box in row:
            snapped.append(
                Box(
                    col=round(box.col, 2),
                    row=top,
                    width=round(box.width, 2),
                    height=height,
                    inferred=box.inferred,
                )
            )
    return snapped


# ---------------------------------------------------------------------------------------
# Guessing which steno key is which
# ---------------------------------------------------------------------------------------

# Assigned outward from the middle of the board, because that is the end that is fixed.
# Every steno layout puts H- and R- against the centre and S- at the far left, so counting
# in from the centre gets a 4-wide and a 5-wide left bank right, where counting from the
# left edge would shift one of them by a key.
_LEFT_TOP = ("H-", "P-", "T-", "S-")
_LEFT_HOME = ("R-", "W-", "K-", "S-")
_RIGHT_TOP = ("-F", "-P", "-L", "-T", "-D")
_RIGHT_HOME = ("-R", "-B", "-G", "-S", "-Z")
_LEFT_THUMB = ("O-", "A-")
_RIGHT_THUMB = ("-E", "-U")


def _split_row(count: int) -> tuple[int, int, int]:
    """How many keys of a main row fall in the left bank, centre column and right bank.

    Counting beats measuring here. English Stenotype fixes the banks at four columns on
    the left (S T P H) and five on the right (F P L T D), so anything past nine keys in a
    row is the asterisk column and nothing else can be. Deciding by x-position instead
    means picking a distance that separates the star from the right bank on every board,
    and no such distance exists -- boards differ by more than the gap does.
    """
    if count >= 9:
        return 4, count - 9, 5
    # A row too short to be a full steno row is split in the same proportion, which keeps
    # a partially detected photo from putting the whole row on one hand.
    left = min(4, max(1, round(count * 4 / 9)))
    return left, 0, count - left


def _members_of(row: list, everything: list) -> list:
    """Every box overlapping a row's band, including tall keys that started higher up.

    A tall key belongs to both rows it covers: the counting rule in `_split_row` needs the
    home row of a stenotype to be ten keys wide, and it only is if the tall S and asterisk
    are counted there as well as in the top row. Assigning such a key twice is harmless --
    it lands on the same steno key from either row, which is the whole point of it being
    one tall key rather than two.
    """
    top = _median([box.row for _index, box in row])
    # The band is one *short* key deep, so a tall key does not stretch it over the row
    # below and swallow it.
    depth = min(box.height for _index, box in row)
    bottom = top + depth
    return [
        pair for pair in everything
        if pair[1].row < bottom - 0.02 and pair[1].row + pair[1].height > top + 0.02
    ]


def _assign(count: int, order: tuple[str, ...]) -> list[str]:
    """Hand out `count` keys from `order`, repeating the last one if the bank is wider.

    A board with more keys in a bank than standard steno has is unusual but real (a spare
    outer column), and repeating the outermost key is the least surprising guess -- the
    same thing a board with two S switches does.
    """
    keys = list(order[:count])
    while len(keys) < count:
        keys.append(order[-1])
    return keys


def infer_keys(boxes: list[Box]) -> list[str]:
    """Guess a steno key for each box from where it sits. Order matches `boxes`.

    Position is all there is to go on, and it is enough for a standard arrangement: rows
    top to bottom, banks left and right of the middle, thumbs on the bottom row. Anything
    unusual comes out wrong, which is exactly what the editor is for.
    """
    if not boxes:
        return []

    indexed = list(enumerate(boxes))
    # Clustered on the top edge, not the centre. A stenotype's tall S and asterisk span
    # both rows, so their centres fall between the rows and would cluster as a row of
    # their own; their top edges line up with the top row exactly as they should.
    rows = _cluster_rows(indexed, lambda pair: pair[1].row, 0.62)
    assigned: dict[int, str] = {}

    left_edge = min(box.col for box in boxes)
    right_edge = max(box.col + box.width for box in boxes)

    # A wide bar spanning most of the board across the top is a number bar, not a row of
    # keys. Taking it out first keeps it from being counted as the top row.
    if len(rows) > 2:
        top = rows[0]
        if len(top) == 1 and top[0][1].width > (right_edge - left_edge) * 0.6:
            assigned[top[0][0]] = "#"
            rows = rows[1:]

    # The bottom row is the thumbs, provided there is a main row above it to be distinct
    # from. A two-row photo is read as the two main rows with no thumbs found.
    thumb_row = rows.pop() if len(rows) >= 3 else []
    main_rows = rows

    # Tall keys are looked up across the whole board, but a number bar already spoken for
    # and the thumbs below must not be dragged into a main row by the overlap test.
    spoken_for = set(assigned) | {index for index, _box in thumb_row}
    pool = [pair for pair in indexed if pair[0] not in spoken_for]

    # Where the centre column sits, learned from the main rows, so the thumbs can be split
    # by the same line the banks were split by rather than by a second guess.
    centre_span: list[float] = []

    for depth, row in enumerate(main_rows):
        ordered = sorted(_members_of(row, pool), key=lambda pair: pair[1].centre[0])
        left_n, centre_n, _right_n = _split_row(len(ordered))
        left = ordered[:left_n]
        centre = ordered[left_n:left_n + centre_n]
        right = ordered[left_n + centre_n:]

        # Depth 0 is the top row, 1 is the home row; a third main row is beyond standard
        # steno, so it repeats the home row rather than inventing keys.
        left_order = _LEFT_TOP if depth == 0 else _LEFT_HOME
        right_order = _RIGHT_TOP if depth == 0 else _RIGHT_HOME

        # The left bank is handed out inward-out: H- and R- sit against the centre on every
        # board, whereas the far edge is where an extra column would appear.
        for (index, _box), key in zip(reversed(left), _assign(len(left), left_order)):
            assigned[index] = key
        for (index, _box), key in zip(right, _assign(len(right), right_order)):
            assigned[index] = key
        for index, box in centre:
            assigned[index] = "*"
            centre_span += [box.col, box.col + box.width]

    if centre_span:
        low, high = min(centre_span), max(centre_span)
    else:
        middle = (left_edge + right_edge) / 2
        low = high = middle

    left_thumbs = sorted(
        (pair for pair in thumb_row if pair[1].centre[0] < low),
        key=lambda pair: pair[1].centre[0], reverse=True,
    )
    right_thumbs = sorted(
        (pair for pair in thumb_row if pair[1].centre[0] > high),
        key=lambda pair: pair[1].centre[0],
    )
    for (index, _box), key in zip(left_thumbs, _assign(len(left_thumbs), _LEFT_THUMB)):
        assigned[index] = key
    for (index, _box), key in zip(right_thumbs, _assign(len(right_thumbs), _RIGHT_THUMB)):
        assigned[index] = key
    # A thumb-row key sitting inside the centre column's span is another asterisk.
    for index, _box in thumb_row:
        assigned.setdefault(index, "*")

    # Anything unclassified falls back to the first steno key, so every box has one and
    # validation has something concrete to complain about.
    return [assigned.get(index, STENO_ORDER[1]) for index in range(len(boxes))]
