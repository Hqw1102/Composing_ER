import pandas as pd
import graphviz
import re
from collections import defaultdict
from html import escape

# ========== 1. 读取数据 ==========
df = pd.read_excel("数据字典_汇总.xlsx")
df.columns = [c.strip() for c in df.columns]

def clean(x):
    return "" if pd.isna(x) else str(x).strip()

def to_bool(x):
    return clean(x).upper() in ["是", "Y", "YES", "TRUE", "1"]

def safe_port(s):
    """
    只用于字段PORT。
    字段大多是英文，可以这样处理。
    """
    return re.sub(r"[^0-9a-zA-Z_]", "_", clean(s))

# ========== 2. 基础字段处理 ==========
df["是否主键_bool"] = df["是否主键"].apply(to_bool)

df["是否外键_bool"] = (
    df["外键-表"].notna()
    & df["外键-字段"].notna()
    & (df["外键-表"].apply(clean) != "")
    & (df["外键-字段"].apply(clean) != "")
)

# ========== 3. 顶层分组：RFQ、partRelease、SAP放一起 ==========
group_map = {
    "RFQ": "RFQ_partRelease_SAP组",
    "partRelease": "RFQ_partRelease_SAP组",
    "SAP": "RFQ_partRelease_SAP组",
}

df["所属系统_clean"] = df["所属系统"].apply(clean)
df["表名_clean"] = df["表名"].apply(clean)
df["顶层分组"] = df["所属系统_clean"].apply(lambda s: group_map.get(s, s))

# ========== 4. 生成唯一表ID，避免中文冲突 ==========
df["表唯一标识"] = df["所属系统_clean"] + "___" + df["表名_clean"]

unique_table_keys = df["表唯一标识"].drop_duplicates().tolist()
table_id_map = {key: f"tbl_{i}" for i, key in enumerate(unique_table_keys)}
df["表唯一标识_id"] = df["表唯一标识"].map(table_id_map)

# ========== 5. 生成唯一cluster ID，避免中文系统名冲突 ==========
unique_top_groups = df["顶层分组"].drop_duplicates().tolist()
top_group_id_map = {
    group: f"cluster_top_{i}"
    for i, group in enumerate(unique_top_groups)
}

unique_systems = df[["顶层分组", "所属系统_clean"]].drop_duplicates()
system_cluster_id_map = {}

for i, row in unique_systems.iterrows():
    top_group = row["顶层分组"]
    system = row["所属系统_clean"]
    system_cluster_id_map[(top_group, system)] = f"cluster_sys_{len(system_cluster_id_map)}"

# ========== 6. 表名映射 ==========
# 默认表名全局唯一；如果后续有不同系统同名表，再改成系统+表名匹配
table_name_to_id = (
    df.drop_duplicates(subset=["表名_clean"])
      .set_index("表名_clean")["表唯一标识_id"]
      .to_dict()
)

table_name_to_cn = (
    df.drop_duplicates(subset=["表名_clean"])
      .set_index("表名_clean")["表名(中文名)"]
      .to_dict()
)

# ========== 7. 找出被外键引用的字段 ==========
referenced_field_map = defaultdict(set)

for _, row in df[df["是否外键_bool"]].iterrows():
    ref_table = clean(row["外键-表"])
    ref_field = clean(row["外键-字段"])
    referenced_field_map[ref_table].add(ref_field)

# ========== 8. 不同系统标题背景色 ==========
system_color_map = {
    "RFQ": "#AED6F1",          # 浅蓝
    "partRelease": "#A9DFBF",  # 浅绿
    "SAP": "#F9E79F",          # 浅黄
}
auto_colors = [
    "#D6EAF8",  # 浅蓝
    "#D5F5E3",  # 浅绿
    "#FCF3CF",  # 浅黄
    "#FADBD8",  # 浅粉
    "#E8DAEF",  # 浅紫
    "#D1F2EB",  # 浅青
    "#FDEBD0",  # 浅橙
    "#EAECEE",  # 浅灰
    "#D4E6F1",  # 灰蓝
    "#F9E79F",  # 淡黄
    "#A9DFBF",  # 淡绿
    "#AED6F1",  # 淡蓝
    "#F5CBA7",  # 淡橙
    "#D7BDE2",  # 淡紫
    "#A3E4D7",  # 淡青
]
all_systems = df["所属系统_clean"].drop_duplicates().tolist()
color_idx = 0
for sys_name in all_systems:
    if sys_name not in system_color_map:
        system_color_map[sys_name] = auto_colors[color_idx % len(auto_colors)]
        color_idx += 1
default_color = "#D5DBDB"

# 如果你想让不同K2子系统也有不同颜色，可以继续加：
# system_color_map.update({
#     "K2_厂内定制委托单": "#FADBD8",
#     "K2_在线领退料申请": "#D6EAF8",
# })

# ========== 9. 创建Graphviz图 ==========
dot = graphviz.Digraph("ER图_总览", format="png", engine="fdp")

dot.attr(
    pack="true",
    packmode="clust",
    overlap="false",
    splines="ortho",
    sep="+25",
    esep="+10",
    fontname="Microsoft YaHei"
)

dot.attr("node", shape="plaintext", fontname="Microsoft YaHei")
dot.attr("edge", fontname="Microsoft YaHei", fontsize="9")

# ========== 10. 创建节点 ==========
for top_group, top_df in df.groupby("顶层分组", sort=False):
    top_cluster_id = top_group_id_map[top_group]

    with dot.subgraph(name=top_cluster_id) as top_c:
        top_c.attr(
            label=top_group,
            style="rounded",
            color="black",
            fontname="Microsoft YaHei",
            fontsize="24",
            penwidth="2",
            margin="25"
        )

        for system, sys_group in top_df.groupby("所属系统_clean", sort=False):
            system_cluster_id = system_cluster_id_map[(top_group, system)]
            title_bg_color = system_color_map.get(system, default_color)

            with top_c.subgraph(name=system_cluster_id) as c:
                c.attr(
                    label=system,
                    style="rounded,dashed",
                    color="gray",
                    fontname="Microsoft YaHei",
                    fontsize="22",
                    margin="15"
                )

                for (table_id, table_name), group in sys_group.groupby(["表唯一标识_id", "表名_clean"], sort=False):
                    group = group.sort_values("序号")

                    table_cn = clean(table_name_to_cn.get(table_name, ""))
                    referenced_set = referenced_field_map.get(table_name, set())

                    rows_html = ""
                    seen_fields = set()

                    for _, row in group.iterrows():
                        field_en = clean(row["字段名(英文)"])

                        if field_en in seen_fields:
                            continue

                        is_pk = row["是否主键_bool"]
                        is_fk = row["是否外键_bool"]
                        is_referenced = field_en in referenced_set

                        # 只展示：主键、外键、被引用字段
                        if not (is_pk or is_fk or is_referenced):
                            continue

                        seen_fields.add(field_en)

                        pk_mark = "🔑" if is_pk else ""
                        fk_mark = "FK" if is_fk else ""

                        rows_html += f"""
                        <TR>
                          <TD PORT="{safe_port(field_en)}" ALIGN="LEFT" CELLPADDING="4">
                            {escape(pk_mark)} {escape(field_en)} {escape(fk_mark)}
                          </TD>
                        </TR>
                        """

                    if rows_html == "":
                        rows_html = """
                        <TR>
                          <TD ALIGN="LEFT" CELLPADDING="4"><I>(无主键/外键)</I></TD>
                        </TR>
                        """

                    # 标题区域：内嵌无边框小表，确保真正居中
                    label = f"""<
                    <TABLE BORDER="1" CELLBORDER="1" CELLSPACING="0">
                      <TR>
                        <TD BGCOLOR="{title_bg_color}" ALIGN="CENTER" CELLPADDING="6">
                          <TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0">
                            <TR>
                              <TD ALIGN="CENTER">
                                <FONT POINT-SIZE="16" FACE="Microsoft YaHei"><B>{escape(table_name)}</B></FONT>
                              </TD>
                            </TR>
                            <TR>
                              <TD ALIGN="CENTER">
                                <FONT POINT-SIZE="14" FACE="Microsoft YaHei"><B>{escape(table_cn)}</B></FONT>
                              </TD>
                            </TR>
                          </TABLE>
                        </TD>
                      </TR>
                      {rows_html}
                    </TABLE>
                    >"""

                    c.node(table_id, label=label)

# ========== 11. 创建表级关系线 ==========
drawn_table_pairs = set()

for _, row in df[df["是否外键_bool"]].iterrows():
    fk_table_id = row["表唯一标识_id"]

    ref_table_name = clean(row["外键-表"])
    ref_table_id = table_name_to_id.get(ref_table_name)

    if not ref_table_id:
        print(
            f"⚠️ 未找到外键关联的表：{ref_table_name}"
            f"（字段 {clean(row['字段名(英文)'])} 所在表 {row['表名']}，系统 {row['所属系统']}）"
        )
        continue

    if ref_table_id == fk_table_id:
        continue

    # 表级去重：同一对表只画一条线
    pair_key = frozenset([fk_table_id, ref_table_id])

    if pair_key in drawn_table_pairs:
        continue

    drawn_table_pairs.add(pair_key)

    dot.edge(
        fk_table_id,
        ref_table_id,
        arrowtail="crow",   # FK表，多端
        arrowhead="tee",    # 被引用表，一端
        dir="both",
        color="darkred"
    )

# ========== 12. 渲染输出 ==========
dot.render("ER图_总览_v6", view=True)
print("ER图已生成：ER图_总览_v6.png")
