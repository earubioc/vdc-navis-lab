// Setup writes: selection sets per discipline, dynamic search sets and clash tests created from the discipline matrix.
// Same safety rules as clash.apply: fingerprint check, nothing is overwritten, everything is verified by rereading.
using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Navisworks.Api;
using Autodesk.Navisworks.Api.Clash;

namespace VdcNavisLab.Addin
{
    internal sealed partial class Handlers
    {
        private const string LabFolder = "VDC Lab";

        // Display names a property can have, English and Spanish Navisworks. The first candidate that matches something wins.
        private static readonly Dictionary<string, string[][]> FieldCandidates = new Dictionary<string, string[][]>
        {
            { "category", new[] { new[] { "Element", "Category" }, new[] { "Elemento", "Categoría" }, new[] { "Item", "Name" }, new[] { "Elemento", "Nombre" } } },
            { "family", new[] { new[] { "Element", "Family" }, new[] { "Elemento", "Familia" } } },
            { "level", new[] { new[] { "Element", "Level" }, new[] { "Elemento", "Nivel" }, new[] { "Elemento", "Capa" }, new[] { "Element", "Layer" } } },
            { "name", new[] { new[] { "Item", "Name" }, new[] { "Elemento", "Nombre" } } },
            { "system", new[] { new[] { "Element", "System Name" }, new[] { "Elemento", "Nombre del sistema" } } },
        };

        private static GroupItem LabFolderOf(Document d, bool create)
        {
            var ss = d.SelectionSets;
            var folder = FindChild(ss.RootItem, LabFolder) as GroupItem;
            if (folder == null && create)
            {
                ss.AddCopy(new FolderItem { DisplayName = LabFolder });
                folder = FindChild(ss.RootItem, LabFolder) as GroupItem;
            }
            return folder;
        }

        private static List<ModelItem> RootsOf(Document d, IEnumerable<string> files)
        {
            var wanted = new HashSet<string>(files, StringComparer.OrdinalIgnoreCase);
            var roots = new List<ModelItem>();
            foreach (var m in d.Models)
                if (wanted.Contains(System.IO.Path.GetFileName(m.FileName ?? ""))) roots.Add(m.RootItem);
            return roots;
        }

        private static ModelItemCollection Collect(IEnumerable<ModelItem> items)
        {
            var c = new ModelItemCollection();
            c.AddRange(items);
            return c;
        }

        private static SearchCondition Condition(string category, string property, string op, string value)
        {
            var c = SearchCondition.HasPropertyByDisplayName(category, property);
            switch (op)
            {
                case "contains": return c.DisplayStringContains(value);
                case "wildcard": return c.DisplayStringWildcard(value);
                default: return c.EqualValue(VariantData.FromDisplayString(value)).IgnoreStringValueCase();
            }
        }

        private static Search NewSearch(Document d)
        {
            var s = new Search();
            s.Selection.SelectAll();
            s.Locations = SearchLocations.DescendantsAndSelf;
            return s;
        }

        private static int CountMatches(Document d, Search s)
        {
            try { return s.FindAll(d, false).Count; } catch { return -1; }
        }

        /// <summary>Resolves one criterion to a SearchCondition that matches something in this document, trying the
        /// candidate property names when only a field (category, level...) was given.</summary>
        private static SearchCondition ResolveCondition(Document d, Dictionary<string, object> c, out string used)
        {
            var op = c.ContainsKey("op") ? Convert.ToString(c["op"]) : "eq";
            var value = Convert.ToString(c["value"]);
            var cat = c.ContainsKey("category") ? Convert.ToString(c["category"]) : "";
            var prop = c.ContainsKey("property") ? Convert.ToString(c["property"]) : "";
            var candidates = new List<string[]>();
            if (cat.Length > 0 && prop.Length > 0) candidates.Add(new[] { cat, prop });
            else
            {
                var field = c.ContainsKey("field") ? Convert.ToString(c["field"]) : "";
                string[][] list;
                if (FieldCandidates.TryGetValue(field, out list)) candidates.AddRange(list);
                else throw new RpcException("invalid_params", "a criterion needs category and property, or a field in category|family|level|name|system");
            }
            foreach (var cand in candidates)
            {
                var test = NewSearch(d);
                SearchCondition cond;
                try { cond = Condition(cand[0], cand[1], op, value); test.SearchConditions.Add(cond); }
                catch { continue; }
                if (CountMatches(d, test) > 0) { used = cand[0] + "/" + cand[1]; return Condition(cand[0], cand[1], op, value); }
            }
            used = "";
            return null;
        }

        public object SetsList()
        {
            return UiThread.Run<object>(() =>
            {
                var d = Doc();
                var rows = new List<object>();
                Action<GroupItem, string> walk = null;
                walk = (parent, path) =>
                {
                    foreach (SavedItem child in parent.Children)
                    {
                        var g = child as GroupItem;
                        var full = path.Length > 0 ? path + "/" + child.DisplayName : child.DisplayName;
                        if (g != null && !(child is SelectionSet)) { rows.Add(new Dictionary<string, object> { { "name", child.DisplayName }, { "path", full }, { "kind", "folder" }, { "children", g.Children.Count() } }); walk(g, full); continue; }
                        var set = child as SelectionSet;
                        if (set == null) continue;
                        var row = new Dictionary<string, object> { { "name", set.DisplayName }, { "path", full }, { "kind", set.HasSearch ? "search" : "explicit" } };
                        try
                        {
                            if (set.HasSearch) { row["conditions"] = set.Search.SearchConditions.Count; row["matches"] = CountMatches(d, set.Search); }
                            else if (set.HasExplicitModelItems) row["items"] = set.ExplicitModelItems.Count;
                        }
                        catch (Exception ex) { row["error"] = ex.GetType().Name; }
                        rows.Add(row);
                    }
                };
                walk(d.SelectionSets.RootItem as GroupItem, "");
                return new Dictionary<string, object> { { "sets", rows } };
            }, 60000);
        }

        /// <summary>Property categories and names of one item (the current selection, or the first leaf of the first
        /// model), so a person can write a search criterion without guessing the localised names.</summary>
        public object PropsSample(Dictionary<string, object> p)
        {
            return UiThread.Run<object>(() =>
            {
                var d = Doc();
                ModelItem item = d.CurrentSelection.SelectedItems.FirstOrDefault();
                if (item == null)
                {
                    var m = d.Models.FirstOrDefault();
                    if (m == null) throw new RpcException("no_document", "the document has no models");
                    item = m.RootItem.DescendantsAndSelf.FirstOrDefault(x => !x.Children.Any());
                }
                var cats = new List<object>();
                foreach (var cat in item.PropertyCategories)
                {
                    var props = new List<object>();
                    foreach (var pr in cat.Properties)
                    {
                        string v; try { v = pr.Value.ToDisplayString(); } catch { v = ""; }
                        if (v.Length > 80) v = v.Substring(0, 80);
                        props.Add(new Dictionary<string, object> { { "name", pr.DisplayName }, { "internal", pr.Name }, { "value", v } });
                    }
                    cats.Add(new Dictionary<string, object> { { "category", cat.DisplayName }, { "internal", cat.Name }, { "properties", props } });
                }
                return new Dictionary<string, object> { { "item", item.DisplayName }, { "from_selection", d.CurrentSelection.SelectedItems.Count > 0 }, { "categories", cats } };
            }, 60000);
        }

        public object SetupApply(Dictionary<string, object> p)
        {
            return UiThread.Run<object>(() =>
            {
                var d = Doc();
                var fp = p.ContainsKey("if_fingerprint") ? Convert.ToString(p["if_fingerprint"]) : "";
                if (fp != Fingerprint(d))
                    throw new RpcException("stale_document", "the open document is not the one the plan was made for", "plan again");
                var missing = new List<string>();
                var notes = new List<string>();
                int setsAdded = 0, setsReused = 0, setsVerified = 0, testsAdded = 0, testsReused = 0, testsVerified = 0;

                var setsArg = p.ContainsKey("sets") ? p["sets"] as System.Collections.ArrayList : null;
                if (setsArg != null && setsArg.Count > 0)
                {
                    GroupItem folder = null;
                    try { folder = LabFolderOf(d, true); }
                    catch (Exception ex) { Log.Write("setup folder failed: " + ex.GetType().Name + ": " + ex.Message); }
                    var parent = folder ?? (GroupItem)d.SelectionSets.RootItem;
                    foreach (var so in setsArg)
                    {
                        var sd = (Dictionary<string, object>)so;
                        var name = Convert.ToString(sd["name"]);
                        try
                        {
                            if (FindChild(parent, name) != null) setsReused++;
                            else
                            {
                                SelectionSet set;
                                if (sd.ContainsKey("models"))
                                {
                                    var roots = RootsOf(d, Strings(sd["models"]));
                                    if (roots.Count == 0) { missing.Add(name + ": ningún modelo coincide"); continue; }
                                    set = new SelectionSet(Collect(roots)) { DisplayName = name };
                                }
                                else
                                {
                                    var search = NewSearch(d);
                                    var crit = sd["where"] as System.Collections.ArrayList;
                                    if (crit == null || crit.Count == 0) { missing.Add(name + ": sin criterios"); continue; }
                                    var failed = false;
                                    foreach (var co in crit)
                                    {
                                        string used;
                                        var cond = ResolveCondition(d, (Dictionary<string, object>)co, out used);
                                        if (cond == null) { missing.Add(name + ": el criterio no encuentra elementos (revise nombres con nw_setup action=properties)"); failed = true; break; }
                                        search.SearchConditions.Add(cond);
                                        notes.Add(name + ": " + used);
                                    }
                                    if (failed) continue;
                                    var n = CountMatches(d, search);
                                    if (n <= 0) { missing.Add(name + ": la combinación de criterios no encuentra elementos"); continue; }
                                    set = new SelectionSet(search) { DisplayName = name };
                                }
                                d.SelectionSets.AddCopy(parent, set);
                                setsAdded++;
                            }
                            var live = FindChild(parent, name) as SelectionSet;
                            if (live != null && ((live.HasExplicitModelItems && live.ExplicitModelItems.Count > 0) || (live.HasSearch && CountMatches(d, live.Search) > 0))) setsVerified++;
                        }
                        catch (Exception ex)
                        {
                            Log.Write("setup set '" + name + "' failed: " + ex.GetType().Name + ": " + ex.Message);
                            missing.Add(name + ": " + ex.GetType().Name);
                        }
                    }
                }

                var testsArg = p.ContainsKey("tests") ? p["tests"] as System.Collections.ArrayList : null;
                if (testsArg != null && testsArg.Count > 0)
                {
                    var edit = d.GetClash().TestsData;
                    foreach (var to in testsArg)
                    {
                        var td = (Dictionary<string, object>)to;
                        var name = Convert.ToString(td["name"]);
                        try
                        {
                            if (Tests(d).Any(t => t.DisplayName == name)) testsReused++;
                            else
                            {
                                var a = RootsOf(d, Strings(td["a"]));
                                var b = RootsOf(d, Strings(td["b"]));
                                if (a.Count == 0 || b.Count == 0) { missing.Add(name + ": falta un lado del cruce en el documento"); continue; }
                                var t = new ClashTest { DisplayName = name };
                                t.TestType = Convert.ToString(td.ContainsKey("type") ? td["type"] : "hard") == "clearance" ? ClashTestType.Clearance : ClashTestType.Hard;
                                var tolM = td.ContainsKey("tolerance_m") ? Convert.ToDouble(td["tolerance_m"]) : 0.001;
                                var f = UnitFactor(d);
                                t.Tolerance = f > 0 ? tolM / f : tolM;
                                t.SelectionA.Selection.CopyFrom(Collect(a));
                                t.SelectionB.Selection.CopyFrom(Collect(b));
                                t.SelectionA.SelfIntersect = false;
                                t.SelectionB.SelfIntersect = false;
                                edit.TestsAddCopy(t);
                                testsAdded++;
                            }
                            var live = Tests(d).FirstOrDefault(x => x.DisplayName == name);
                            if (live != null && live.SelectionA.Selection.HasExplicitSelection && live.SelectionB.Selection.HasExplicitSelection) testsVerified++;
                        }
                        catch (Exception ex)
                        {
                            Log.Write("setup test '" + name + "' failed: " + ex.GetType().Name + ": " + ex.Message);
                            missing.Add(name + ": " + ex.GetType().Name);
                        }
                    }
                }
                return new Dictionary<string, object>
                {
                    { "applied", new Dictionary<string, object> { { "sets_added", setsAdded }, { "sets_reused", setsReused }, { "tests_added", testsAdded }, { "tests_reused", testsReused } } },
                    { "verified", new Dictionary<string, object> { { "sets", setsVerified }, { "tests", testsVerified } } },
                    { "missing", missing }, { "notes", notes }
                };
            }, 300000);
        }
    }
}
