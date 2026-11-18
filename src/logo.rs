//! brewcat logo: a black cat on an amber badge. Drawn from shapes, so the window needs no image file at run time.
//! The same shapes produced `assets/brewcat.png` and the `.icns`.

type Rgb = [u8; 3];

enum Shape {
    Tri([(f64, f64); 3], Rgb),
    /// centre x, centre y, radius x, radius y
    Oval(f64, f64, f64, f64, Rgb),
}

/// Corner radius of the badge (unit coordinates).
const BADGE_RADIUS: f64 = 0.22;
const BADGE_COLOR: Rgb = [0xf2, 0xb8, 0x4b];
const BLACK: Rgb = [0x11, 0x11, 0x11];
const PINK: Rgb = [0xe5, 0x8a, 0xa0];
const GREEN: Rgb = [0x7b, 0xe2, 0x6b];

/// Shapes in unit coordinates (0..1), painted back to front.
const SHAPES: [Shape; 10] = [
    Shape::Tri([(0.20, 0.48), (0.21, 0.14), (0.44, 0.33)], BLACK),
    Shape::Tri([(0.80, 0.48), (0.79, 0.14), (0.56, 0.33)], BLACK),
    Shape::Tri([(0.26, 0.40), (0.27, 0.24), (0.38, 0.34)], PINK),
    Shape::Tri([(0.74, 0.40), (0.73, 0.24), (0.62, 0.34)], PINK),
    Shape::Oval(0.5, 0.60, 0.33, 0.28, BLACK),
    Shape::Oval(0.37, 0.56, 0.075, 0.055, GREEN),
    Shape::Oval(0.63, 0.56, 0.075, 0.055, GREEN),
    Shape::Oval(0.37, 0.56, 0.014, 0.05, BLACK),
    Shape::Oval(0.63, 0.56, 0.014, 0.05, BLACK),
    Shape::Tri([(0.46, 0.66), (0.54, 0.66), (0.5, 0.71)], PINK),
];

fn in_tri(p: (f64, f64), a: (f64, f64), b: (f64, f64), c: (f64, f64)) -> bool {
    let side = |p1: (f64, f64), p2: (f64, f64), p3: (f64, f64)| (p1.0 - p3.0) * (p2.1 - p3.1) - (p2.0 - p3.0) * (p1.1 - p3.1);
    let (d1, d2, d3) = (side(p, a, b), side(p, b, c), side(p, c, a));
    !((d1 < 0.0 || d2 < 0.0 || d3 < 0.0) && (d1 > 0.0 || d2 > 0.0 || d3 > 0.0))
}

fn in_round(x: f64, y: f64, r: f64) -> bool {
    let (cx, cy) = (x.max(r).min(1.0 - r), y.max(r).min(1.0 - r));
    (x - cx).powi(2) + (y - cy).powi(2) <= r * r
}

/// The colour at a point of the unit square, or None outside the badge. Later shapes cover earlier ones.
fn color_at(x: f64, y: f64) -> Option<Rgb> {
    if !in_round(x, y, BADGE_RADIUS) {
        return None;
    }
    let mut col = BADGE_COLOR;
    for shape in &SHAPES {
        match shape {
            Shape::Tri([a, b, c], color) if in_tri((x, y), *a, *b, *c) => col = *color,
            Shape::Oval(cx, cy, rx, ry, color) if ((x - cx) / rx).powi(2) + ((y - cy) / ry).powi(2) <= 1.0 => col = *color,
            _ => {}
        }
    }
    Some(col)
}

/// The logo as straight (non-premultiplied) RGBA, `size` x `size` pixels, supersampled `ss` x `ss` per pixel.
pub fn rasterize(size: usize, ss: usize) -> Vec<u8> {
    let mut rgba = Vec::with_capacity(size * size * 4);
    let n = (ss * ss) as u32;
    for j in 0..size {
        for i in 0..size {
            let (mut acc, mut covered) = ([0u32; 3], 0u32);
            for sj in 0..ss {
                for si in 0..ss {
                    let x = (i as f64 + (si as f64 + 0.5) / ss as f64) / size as f64;
                    let y = (j as f64 + (sj as f64 + 0.5) / ss as f64) / size as f64;
                    if let Some(c) = color_at(x, y) {
                        covered += 1;
                        (0..3).for_each(|k| acc[k] += u32::from(c[k]));
                    }
                }
            }
            let k = covered.max(1);
            let alpha = (covered * 255 / n) as u8;
            rgba.extend_from_slice(&[(acc[0] / k) as u8, (acc[1] / k) as u8, (acc[2] / k) as u8, alpha]);
        }
    }
    rgba
}

#[cfg(test)]
mod tests {
    use super::*;

    fn px(rgba: &[u8], size: usize, x: usize, y: usize) -> [u8; 4] {
        let o = (y * size + x) * 4;
        [rgba[o], rgba[o + 1], rgba[o + 2], rgba[o + 3]]
    }

    #[test]
    fn corners_are_transparent_and_the_badge_is_amber() {
        let img = rasterize(64, 2);
        assert_eq!(img.len(), 64 * 64 * 4);
        assert_eq!(px(&img, 64, 0, 0)[3], 0); // rounded corner
        assert_eq!(px(&img, 64, 63, 63)[3], 0);
        assert_eq!(px(&img, 64, 32, 4), [0xf2, 0xb8, 0x4b, 255]); // badge, above the cat
    }

    #[test]
    fn the_cat_is_black_with_green_eyes() {
        let img = rasterize(100, 3);
        assert_eq!(px(&img, 100, 50, 80), [0x11, 0x11, 0x11, 255]); // face
        let eye = px(&img, 100, 33, 56); // left eye, away from the pupil
        assert_eq!(eye, [0x7b, 0xe2, 0x6b, 255]);
        assert_eq!(px(&img, 100, 50, 68), [0xe5, 0x8a, 0xa0, 255]); // nose
    }
}
