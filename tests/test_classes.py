from breakwater.classes import group_classes, split

INV = "P2|outcome|exc:packaging.version.InvalidVersion|ok"


def test_traits_supersets_fold_into_the_simpler_class():
    sigs = [f"{INV}|long-digits+whitespace", f"{INV}|long-digits", "P1|len|differs|plain", "P1|len|differs|whitespace"]
    groups = group_classes(sigs)
    assert [(g.primary, g.duplicates) for g in groups] == [
        (f"{INV}|long-digits", [f"{INV}|long-digits+whitespace"]),
        ("P1|len|differs|plain", ["P1|len|differs|whitespace"]),
    ]


def test_combinations_never_merge_distinct_traits():
    # #1082's intermediate commit: Unicode digits and inner whitespace were separate bugs.
    sigs = [f"{INV}|non-ascii", f"{INV}|whitespace", f"{INV}|non-ascii+whitespace"]
    groups = group_classes(sigs)
    assert [g.primary for g in groups] == [f"{INV}|non-ascii", f"{INV}|whitespace"]
    assert all(g.shared == [f"{INV}|non-ascii+whitespace"] for g in groups)


def test_labels_and_structure_separate_groups():
    sigs = [f"{INV}|plain", f"{INV}|whitespace", "P2|outcome|exc:builtins.ValueError|ok|whitespace"]
    labels = {f"{INV}|whitespace": "intended"}
    assert len(group_classes(sigs, labels)) == 3  # different label; different outcome shape


def test_ordering_flips_are_one_group_and_equality_stays_separate():
    sigs = ["P3|gt|True|False", "P3|lt|False|True", "P3|eq|True|False", "P3|hash_eq|True|False"]
    groups = group_classes(sigs, size={"P3|lt|False|True": 1, "P3|gt|True|False": 5})
    assert [g.members for g in groups] == [["P3|lt|False|True", "P3|gt|True|False"], ["P3|eq|True|False"],
                                           ["P3|hash_eq|True|False"]]
    assert split("P4|base->head load|loads|exc:builtins.AttributeError")[1] == frozenset()


def test_markdown_report_groups_near_duplicates():
    from breakwater.adversary import AuditReport, Finding, render_markdown

    fs = [Finding(f"{INV}|non-ascii", "P2", "outcome", [["\u0661"]], {"status": "exc"}, {"status": "ok"}, ["A1/s1"]),
          Finding(f"{INV}|long-digits+non-ascii", "P2", "outcome", [["\u0661" * 3]], {"status": "exc"}, {"status": "ok"}, ["seed"])]
    md = render_markdown(AuditReport("r", "repo", "b" * 10, "h" * 10, "t", "img", "docker", [], [], fs, {}, {}))
    assert "2 classes in 1 group of near-duplicates." in md and md.count("- **[P2] outcome**") == 1
    assert "near-duplicates:" in md
