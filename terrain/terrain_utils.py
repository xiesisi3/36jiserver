import math


def segments_cross(p1, q1, p2, q2):
    if p1 == p2 or p1 == q2 or q1 == p2 or q1 == q2:
        return False

    def _cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1 = _cross(p1, p2, q2)
    d2 = _cross(q1, p2, q2)
    d3 = _cross(p2, p1, q1)
    d4 = _cross(q2, p1, q1)

    if ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4)):
        return True
    if d1 == 0 and min(p2[0], q2[0]) <= p1[0] <= max(p2[0], q2[0]) and min(p2[1], q2[1]) <= p1[1] <= max(p2[1], q2[1]):
        return True
    if d2 == 0 and min(p2[0], q2[0]) <= q1[0] <= max(p2[0], q2[0]) and min(p2[1], q2[1]) <= q1[1] <= max(p2[1], q2[1]):
        return True
    if d3 == 0 and min(p1[0], q1[0]) <= p2[0] <= max(p1[0], q1[0]) and min(p1[1], q1[1]) <= p2[1] <= max(p1[1], q1[1]):
        return True
    if d4 == 0 and min(p1[0], q1[0]) <= q2[0] <= max(p1[0], q1[0]) and min(p1[1], q1[1]) <= q2[1] <= max(p1[1], q1[1]):
        return True
    return False


def point_in_polygon(px, py, vertices):
    inside = False
    n = len(vertices)
    j = n - 1
    for i in range(n):
        xi, yi = vertices[i]
        xj, yj = vertices[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def polygon_bbox(vertices):
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    return min(xs), min(ys), max(xs), max(ys)


def grid_to_position(row, col, margin, cell_width, cell_height):
    center_x = margin + col * cell_width + cell_width // 2
    center_y = margin + row * cell_height + cell_height // 2
    return center_x, center_y


def position_to_grid(px, py, margin, cell_width, cell_height):
    col = round((px - margin - cell_width // 2) / cell_width)
    row = round((py - margin - cell_height // 2) / cell_height)
    return row, col


def river_blocks_edge(edge_p1, edge_p2, rivers):
    for river in rivers:
        for i in range(len(river) - 1):
            rp1 = river[i]
            rp2 = river[i + 1]
            if segments_cross(edge_p1, edge_p2, rp1, rp2):
                return True
    return False