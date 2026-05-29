"""MCP server for spreadsheet / report processing (Excel, CSV)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
from fastmcp import FastMCP
from fastmcp.prompts import Message

mcp = FastMCP("report-processor")

SUPPORTED = {".xlsx", ".xls", ".csv"}
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/data/uploads"))
FILTER_OPERATORS = ("eq", "ne", "gt", "gte", "lt", "lte", "contains")
AGG_FUNCTIONS = ("sum", "mean", "count", "max", "min")

REPORT_GUIDE = {
    "supported_formats": sorted(SUPPORTED),
    "upload_dir": str(UPLOAD_DIR),
    "filter_operators": {
        "eq": "equals",
        "ne": "not equals",
        "gt": "greater than (numeric)",
        "gte": "greater than or equal",
        "lt": "less than",
        "lte": "less than or equal",
        "contains": "substring match (case-insensitive)",
    },
    "aggregate_functions": list(AGG_FUNCTIONS),
    "tools": {
        "report_summary": "Overview: shape, columns, dtypes, missing, numeric stats",
        "report_filter": "Filter rows and export",
        "report_aggregate": "Group-by aggregation",
        "report_top_n": "Top N rows by column",
    },
    "resources": {
        "report://guide": "This reference document",
        "report://uploads": "List spreadsheets in the upload directory",
        "report://file/{filename}": "Preview first rows of a file by basename in upload dir",
    },
    "prompts": {
        "analyze_report": "Full analysis workflow for a spreadsheet",
        "filter_report": "Structured filter task for a spreadsheet",
    },
}


def _resolve_upload_file(filename: str) -> Path:
    """Resolve a basename within UPLOAD_DIR (no path traversal)."""
    name = Path(filename).name
    if not name or name in {".", ".."}:
        raise ValueError("Invalid filename")
    path = (UPLOAD_DIR / name).resolve()
    if not str(path).startswith(str(UPLOAD_DIR.resolve())):
        raise ValueError("Path traversal is not allowed")
    if not path.exists():
        raise FileNotFoundError(f"File not found in uploads: {name}")
    return path


def _load_df(file_path: str) -> pd.DataFrame:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if path.suffix.lower() not in SUPPORTED:
        raise ValueError(f"Unsupported format: {path.suffix}. Use xlsx/xls/csv.")

    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


@mcp.tool()
def report_summary(file_path: str, sheet_name: str | None = None) -> str:
    """Summarize a spreadsheet: shape, columns, dtypes, missing values, and numeric stats."""
    path = Path(file_path)
    if path.suffix.lower() in {".xlsx", ".xls"} and sheet_name:
        df = pd.read_excel(path, sheet_name=sheet_name)
    else:
        df = _load_df(file_path)

    summary: dict = {
        "rows": len(df),
        "columns": list(df.columns.astype(str)),
        "dtypes": {str(k): str(v) for k, v in df.dtypes.items()},
        "missing": {str(k): int(v) for k, v in df.isna().sum().items() if v > 0},
    }
    numeric = df.select_dtypes(include="number")
    if not numeric.empty:
        summary["numeric_stats"] = json.loads(numeric.describe().to_json())
    return json.dumps(summary, ensure_ascii=False, indent=2)


@mcp.tool()
def report_filter(
    file_path: str,
    column: str,
    operator: str,
    value: str,
    output_path: str | None = None,
) -> str:
    """Filter rows. operator: eq, ne, gt, gte, lt, lte, contains."""
    df = _load_df(file_path)
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found. Available: {list(df.columns)}")

    col = df[column]
    ops = {
        "eq": col.astype(str) == value,
        "ne": col.astype(str) != value,
        "contains": col.astype(str).str.contains(value, case=False, na=False),
        "gt": col > float(value),
        "gte": col >= float(value),
        "lt": col < float(value),
        "lte": col <= float(value),
    }
    if operator not in ops:
        raise ValueError(f"Unknown operator: {operator}")

    filtered = df[ops[operator]]
    out = output_path or str(Path(file_path).with_stem(Path(file_path).stem + "_filtered"))
    filtered.to_excel(out, index=False) if out.endswith((".xlsx", ".xls")) else filtered.to_csv(out, index=False)
    return json.dumps(
        {"matched_rows": len(filtered), "output_path": out, "preview": filtered.head(10).to_dict(orient="records")},
        ensure_ascii=False,
        default=str,
    )


@mcp.tool()
def report_aggregate(
    file_path: str,
    group_by: str,
    agg_column: str,
    agg_func: str = "sum",
) -> str:
    """Group by column and aggregate (sum, mean, count, max, min)."""
    df = _load_df(file_path)
    for col in (group_by, agg_column):
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found.")

    result = df.groupby(group_by)[agg_column].agg(agg_func).reset_index()
    return result.to_json(orient="records", force_ascii=False)


@mcp.tool()
def report_top_n(
    file_path: str,
    sort_column: str,
    n: int = 10,
    ascending: bool = False,
) -> str:
    """Return top N rows sorted by a column."""
    df = _load_df(file_path)
    if sort_column not in df.columns:
        raise ValueError(f"Column '{sort_column}' not found.")
    top = df.sort_values(sort_column, ascending=ascending).head(n)
    return top.to_json(orient="records", force_ascii=False, default=str)


# --- MCP Resources ---


@mcp.resource(
    "report://guide",
    name="report_guide",
    description="Reference for supported formats, operators, tools, and URIs",
    mime_type="application/json",
)
def report_guide() -> str:
    """Static guide for agents working with spreadsheet reports."""
    return json.dumps(REPORT_GUIDE, ensure_ascii=False, indent=2)


@mcp.resource(
    "report://uploads",
    name="report_uploads",
    description="Catalog of spreadsheet files available in the upload directory",
    mime_type="application/json",
)
def report_uploads() -> str:
    """List Excel/CSV files in UPLOAD_DIR with size and modified time."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    for path in sorted(UPLOAD_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED:
            continue
        stat = path.stat()
        entries.append(
            {
                "filename": path.name,
                "uri": f"report://file/{path.name}",
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
            }
        )
    return json.dumps(
        {"upload_dir": str(UPLOAD_DIR), "files": entries, "count": len(entries)},
        ensure_ascii=False,
        indent=2,
    )


@mcp.resource(
    "report://file/{filename}",
    name="report_file_preview",
    description="Preview first rows and schema of a spreadsheet by filename (basename in upload dir)",
    mime_type="application/json",
)
def report_file_preview(filename: str) -> str:
    """Read a lightweight preview of an uploaded report for context before tool calls."""
    path = _resolve_upload_file(filename)
    df = _load_df(str(path))
    preview_rows = 20
    payload = {
        "filename": path.name,
        "path": str(path),
        "rows_total": len(df),
        "columns": list(df.columns.astype(str)),
        "preview": df.head(preview_rows).to_dict(orient="records"),
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


# --- MCP Prompts ---


@mcp.prompt(
    name="analyze_report",
    description="Generate a user message that drives full spreadsheet analysis via MCP tools",
)
def analyze_report(
    file_path: str,
    question: str = "请全面分析该报表：概览、关键指标、异常与建议。",
) -> list[Message]:
    """Prompt template for end-to-end report analysis."""
    return [
        Message(
            role="user",
            content=(
                f"请分析报表文件：{file_path}\n\n"
                f"用户问题：{question}\n\n"
                "建议步骤：\n"
                "1. 调用 report_summary 获取结构与统计\n"
                "2. 按需调用 report_aggregate / report_top_n 深入分析\n"
                "3. 用中文给出简洁结论，并注明数据来源"
            ),
        )
    ]


@mcp.prompt(
    name="filter_report",
    description="Generate a user message for filtering and exporting spreadsheet rows",
)
def filter_report(
    file_path: str,
    column: str,
    operator: str,
    value: str,
    output_path: str | None = None,
) -> list[Message]:
    """Prompt template for filter-and-export workflows."""
    ops_hint = ", ".join(FILTER_OPERATORS)
    out_line = f"\n输出路径：{output_path}" if output_path else ""
    return [
        Message(
            role="user",
            content=(
                f"请筛选报表 {file_path}：\n"
                f"- 列：{column}\n"
                f"- 运算符：{operator}（可选: {ops_hint}）\n"
                f"- 值：{value}"
                f"{out_line}\n\n"
                "请调用 report_filter 完成筛选，并总结匹配行数与结果预览。"
            ),
        )
    ]


if __name__ == "__main__":
    import os

    transport = os.getenv("MCP_TRANSPORT", "stdio").lower().replace("_", "-")
    if transport in {"http", "streamable-http", "streamablehttp"}:
        host = os.getenv("MCP_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_PORT", "8000"))
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        mcp.run(transport="stdio")
