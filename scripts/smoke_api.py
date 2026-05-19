from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import app


def main() -> None:
    with TestClient(app) as client:
        r = client.get("/health")
        print("health", r.status_code, r.json())

        r = client.post(
            "/ask",
            json={
                "question": "劳动合同解除一般需要提前多久通知？请结合检索依据说明。",
            },
        )
        print("ask", r.status_code)
        print(r.text[:2000])

        # Direction 3: 多米诺效应检测
        r = client.get("/domino_impact/stats")
        print("domino_impact/stats", r.status_code, r.json())

        r = client.post(
            "/domino_impact",
            json={
                "law_title": "中华人民共和国合同法",
                "article_no": "第六十一条",
            },
        )
        d = r.json()
        print(
            "domino_impact",
            r.status_code,
            f"trigger={d['trigger_node']}",
            f"direct={len(d['direct_impacts'])}",
            f"indirect={len(d['indirect_impacts'])}",
        )

        # 递归 + 边界：不存在的法律
        r = client.post(
            "/domino_impact",
            json={
                "law_title": "中华人民共和国宇宙飞船法",
                "article_no": "第一条",
                "recursive": True,
            },
        )
        d = r.json()
        print(
            "domino_impact(not_found)",
            r.status_code,
            f"total={d['total_affected_articles']}",
        )

        # Direction 4: 反事实模拟
        r = client.get("/counterfactual/directions")
        print("counterfactual/directions", r.status_code, f"count={len(r.json().get('directions', []))}")

        r = client.post(
            "/counterfactual",
            json={
                "law_title": "中华人民共和国劳动合同法",
                "article_no": "第三十八条",
                "direction": "obligation_decrease",
                "magnitude": "中等",
                "include_indirect": False,
                "max_depth": 1,
            },
        )
        d = r.json()
        print(
            "counterfactual(structured)",
            r.status_code,
            f"interpreted={d['interpreted_direction']}",
            f"direct={len(d['direct_impacts'])}",
            f"indirect={len(d['indirect_impacts'])}",
            f"total={d['total_affected']}",
        )
        if d["direct_impacts"]:
            imp = d["direct_impacts"][0]
            print(f"  -> {imp['law_title']} {imp['article_no']} [{imp['risk_level']}]")

        r = client.post(
            "/counterfactual",
            json={
                "law_title": "中华人民共和国劳动合同法",
                "article_no": "第三十八条",
                "direction": "保护企业灵活性，减轻义务",
                "magnitude": "中等",
            },
        )
        d = r.json()
        print(
            "counterfactual(natural)",
            r.status_code,
            f"interpreted={d['interpreted_direction']}",
            f"total={d['total_affected']}",
        )

        # 边界：不存在法律
        r = client.post(
            "/counterfactual",
            json={
                "law_title": "中华人民共和国宇宙飞船法",
                "article_no": "第一条",
                "direction": "保护乘客",
            },
        )
        d = r.json()
        print("counterfactual(not_found)", r.status_code, f"total={d['total_affected']}")


if __name__ == "__main__":
    main()
