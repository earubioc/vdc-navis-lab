// Oriented box of an element, from its real triangles (COM API), for beams and straight runs.
// Navisworks only exposes an axis-aligned box through the .NET API, which says nothing about the direction of a
// diagonal beam or a conduit. The result is checked against the box Navisworks itself reports; if they disagree the
// element simply gets no orientation (the engine then leaves its priority alone).
using System;
using System.Collections.Generic;
using Autodesk.Navisworks.Api;
using Autodesk.Navisworks.Api.ComApi;
using ComApi = Autodesk.Navisworks.Api.Interop.ComApi;

namespace VdcNavisLab.Addin
{
    internal sealed class VertexCollector : ComApi.InwSimplePrimitivesCB
    {
        public readonly List<double> Local = new List<double>();
        public int Limit = 400000;

        private void Add(ComApi.InwSimpleVertex v)
        {
            if (Local.Count >= Limit) return;
            var c = (Array)(object)v.coord;
            int lo = c.GetLowerBound(0);
            Local.Add(Convert.ToDouble(c.GetValue(lo)));
            Local.Add(Convert.ToDouble(c.GetValue(lo + 1)));
            Local.Add(Convert.ToDouble(c.GetValue(lo + 2)));
        }

        public void Triangle(ComApi.InwSimpleVertex v1, ComApi.InwSimpleVertex v2, ComApi.InwSimpleVertex v3) { Add(v1); Add(v2); Add(v3); }
        public void Line(ComApi.InwSimpleVertex v1, ComApi.InwSimpleVertex v2) { }
        public void Point(ComApi.InwSimpleVertex v1) { }
        public void SnapPoint(ComApi.InwSimpleVertex v1) { }
    }

    internal static class Orientation
    {
        private static int _reported;

        /// <summary>Why the last Compute returned null (for diagnostics in the export, not for users).</summary>
        public static string LastStatus = "";

        /// <summary>Oriented box in document units, or null: centre, three unit axes (the first is the longest)
        /// and half extents along them.</summary>
        public static double[][] Compute(ModelItem item, BoundingBox3D worldBox)
        {
            try
            {
                LastStatus = "";
                var pts = WorldPoints(item, worldBox);
                if (pts == null || pts.Count < 9) { if (LastStatus.Length == 0) LastStatus = "no points"; return null; }
                return Fit(pts);
            }
            catch (Exception ex)
            {
                LastStatus = "exception " + ex.GetType().Name + ": " + ex.Message;
                if (_reported++ < 5) Log.Write("orientation failed: " + LastStatus);
                return null;
            }
        }

        private static List<double> WorldPoints(ModelItem item, BoundingBox3D box)
        {
            var path = ComApiBridge.ToInwOaPath(item);
            var perFragment = new List<KeyValuePair<List<double>, double[]>>();
            foreach (ComApi.InwOaFragment3 frag in path.Fragments())
            {
                var cb = new VertexCollector();
                frag.GenerateSimplePrimitives(ComApi.nwEVertexProperty.eNONE, cb);
                if (cb.Local.Count == 0) continue;
                var xf = (ComApi.InwLTransform3f3)frag.GetLocalToWorldMatrix();
                var m = (Array)(object)xf.Matrix;
                int lo = m.GetLowerBound(0);
                var mat = new double[16];
                for (int i = 0; i < 16; i++) mat[i] = Convert.ToDouble(m.GetValue(lo + i));
                perFragment.Add(new KeyValuePair<List<double>, double[]>(cb.Local, mat));
            }
            if (perFragment.Count == 0) { LastStatus = "no fragments"; return null; }
            // Two layouts exist in the wild (translation in the last row, or in the last column): keep the one whose
            // result fits the box Navisworks reports for this very item, and fits it best.
            List<double> best = null; double bestFit = 0; string why = "";
            foreach (var rowMajor in new[] { true, false })
            {
                var pts = new List<double>();
                foreach (var kv in perFragment)
                {
                    var l = kv.Key; var m = kv.Value;
                    for (int i = 0; i + 2 < l.Count; i += 3)
                    {
                        double x = l[i], y = l[i + 1], z = l[i + 2];
                        if (rowMajor)
                        {
                            pts.Add(m[0] * x + m[4] * y + m[8] * z + m[12]);
                            pts.Add(m[1] * x + m[5] * y + m[9] * z + m[13]);
                            pts.Add(m[2] * x + m[6] * y + m[10] * z + m[14]);
                        }
                        else
                        {
                            pts.Add(m[0] * x + m[1] * y + m[2] * z + m[3]);
                            pts.Add(m[4] * x + m[5] * y + m[6] * z + m[7]);
                            pts.Add(m[8] * x + m[9] * y + m[10] * z + m[11]);
                        }
                    }
                }
                string note;
                double fit = Fit(pts, box, out note);
                why += (rowMajor ? "row:" : "col:") + note + " ";
                if (fit > bestFit) { bestFit = fit; best = pts; }
            }
            if (best == null) LastStatus = "box mismatch " + why.Trim();
            return best;
        }

        /// <summary>0 when the points do not fit the item's box; otherwise how much of it they fill (0..1).
        /// Navisworks' item box is the transformed local box, so for a rotated element it is looser than the exact
        /// extent of the triangles: the triangles must lie inside it, not equal it.</summary>
        private static double Fit(List<double> pts, BoundingBox3D box, out string note)
        {
            double[] lo = { double.MaxValue, double.MaxValue, double.MaxValue }, hi = { double.MinValue, double.MinValue, double.MinValue };
            for (int i = 0; i + 2 < pts.Count; i += 3)
                for (int k = 0; k < 3; k++) { lo[k] = Math.Min(lo[k], pts[i + k]); hi[k] = Math.Max(hi[k], pts[i + k]); }
            double[] bl = { box.Min.X, box.Min.Y, box.Min.Z }, bh = { box.Max.X, box.Max.Y, box.Max.Z };
            double fill = 1;
            note = "";
            for (int k = 0; k < 3; k++)
            {
                double size = Math.Max(bh[k] - bl[k], 1e-6);
                double tol = 0.02 * size + 1e-4;
                if (lo[k] < bl[k] - tol || hi[k] > bh[k] + tol)
                {
                    note = "outside axis " + k + " pts=[" + Math.Round(lo[k], 2) + "," + Math.Round(hi[k], 2) + "] box=[" + Math.Round(bl[k], 2) + "," + Math.Round(bh[k], 2) + "]";
                    return 0;
                }
                fill *= Math.Max(0.01, Math.Min(1.0, (hi[k] - lo[k]) / size));
            }
            note = "ok fill=" + Math.Round(fill, 3);
            return fill;
        }

        // ---- fitting: longest principal axis by PCA, then the minimum-area rectangle in the cross-section plane.
        private static double[][] Fit(List<double> p)
        {
            int n = p.Count / 3;
            double mx = 0, my = 0, mz = 0;
            for (int i = 0; i < n; i++) { mx += p[3 * i]; my += p[3 * i + 1]; mz += p[3 * i + 2]; }
            mx /= n; my /= n; mz /= n;
            double[,] c = new double[3, 3];
            for (int i = 0; i < n; i++)
            {
                double[] d = { p[3 * i] - mx, p[3 * i + 1] - my, p[3 * i + 2] - mz };
                for (int a = 0; a < 3; a++) for (int b = 0; b < 3; b++) c[a, b] += d[a] * d[b];
            }
            var axis = Dominant(c);
            // Perpendicular basis: e1 horizontal when the axis is not vertical, else world X.
            double[] z = { 0, 0, 1 };
            double[] e1 = Cross(axis, z);
            if (Norm(e1) < 1e-6) e1 = new double[] { 1, 0, 0 };
            e1 = Unit(e1);
            double[] e2 = Unit(Cross(axis, e1));

            double bestArea = double.MaxValue; double bestAng = 0;
            double[] bestRange = null;
            for (int deg = 0; deg < 90; deg++)
            {
                double ang = deg * Math.PI / 180.0, ca = Math.Cos(ang), sa = Math.Sin(ang);
                double u0 = double.MaxValue, u1 = double.MinValue, v0 = double.MaxValue, v1 = double.MinValue;
                for (int i = 0; i < n; i++)
                {
                    double dx = p[3 * i] - mx, dy = p[3 * i + 1] - my, dz = p[3 * i + 2] - mz;
                    double s = dx * e1[0] + dy * e1[1] + dz * e1[2], t = dx * e2[0] + dy * e2[1] + dz * e2[2];
                    double u = ca * s + sa * t, v = -sa * s + ca * t;
                    if (u < u0) u0 = u; if (u > u1) u1 = u; if (v < v0) v0 = v; if (v > v1) v1 = v;
                }
                double area = (u1 - u0) * (v1 - v0);
                if (area < bestArea) { bestArea = area; bestAng = ang; bestRange = new[] { u0, u1, v0, v1 }; }
            }
            double cb = Math.Cos(bestAng), sb = Math.Sin(bestAng);
            double[] ax1 = { cb * e1[0] + sb * e2[0], cb * e1[1] + sb * e2[1], cb * e1[2] + sb * e2[2] };
            double[] ax2 = { -sb * e1[0] + cb * e2[0], -sb * e1[1] + cb * e2[1], -sb * e1[2] + cb * e2[2] };
            // extent along the main axis
            double a0 = double.MaxValue, a1 = double.MinValue;
            for (int i = 0; i < n; i++)
            {
                double s = (p[3 * i] - mx) * axis[0] + (p[3 * i + 1] - my) * axis[1] + (p[3 * i + 2] - mz) * axis[2];
                if (s < a0) a0 = s; if (s > a1) a1 = s;
            }
            // centre of the box (not of the vertex cloud)
            double ca0 = (a0 + a1) / 2, cu = (bestRange[0] + bestRange[1]) / 2, cv = (bestRange[2] + bestRange[3]) / 2;
            double[] centre = {
                mx + ca0 * axis[0] + cu * ax1[0] + cv * ax2[0],
                my + ca0 * axis[1] + cu * ax1[1] + cv * ax2[1],
                mz + ca0 * axis[2] + cu * ax1[2] + cv * ax2[2] };
            return new[] { centre, axis, ax1, ax2,
                new[] { (a1 - a0) / 2, (bestRange[1] - bestRange[0]) / 2, (bestRange[3] - bestRange[2]) / 2 } };
        }

        private static double[] Dominant(double[,] c)
        {
            double[] v = { 0.577, 0.577, 0.577 };
            for (int it = 0; it < 60; it++)
            {
                double[] w = new double[3];
                for (int a = 0; a < 3; a++) w[a] = c[a, 0] * v[0] + c[a, 1] * v[1] + c[a, 2] * v[2];
                double nrm = Norm(w);
                if (nrm < 1e-12) break;
                v = new[] { w[0] / nrm, w[1] / nrm, w[2] / nrm };
            }
            return v;
        }

        private static double Norm(double[] a) { return Math.Sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]); }
        private static double[] Unit(double[] a) { double n = Norm(a); return n < 1e-12 ? a : new[] { a[0] / n, a[1] / n, a[2] / n }; }
        private static double[] Cross(double[] a, double[] b) { return new[] { a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0] }; }
    }
}
