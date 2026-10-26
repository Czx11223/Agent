import { useMemo } from "react";
import { Button, Card, Tag, Typography } from "antd";
import { CopyOutlined, DownloadOutlined } from "@ant-design/icons";
import ReactMarkdown from "react-markdown";

const { Title, Paragraph, Text } = Typography;

export interface Report {
  chief_complaint?: string | null;
  present_illness?: string | null;
  allergy_history?: string | null;
  past_history?: string | null;
  recommend_dept_top3?: string | null;
  disclaimer?: string | null;
}

interface Dept { dept: string; reason?: string }

function parseDepts(raw?: string | null): Dept[] {
  if (!raw) return [];
  try {
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? (arr as Dept[]) : [];
  } catch {
    return [{ dept: raw }];
  }
}

const DISCLAIMER =
  "本预问诊报告仅用于挂号与接诊参考，不构成医学诊断或治疗建议，最终请以执业医师判断为准。";

export function ReportPanel({ report }: { report: Report }) {
  const depts = useMemo(() => parseDepts(report.recommend_dept_top3), [report.recommend_dept_top3]);

  const md = useMemo(
    () =>
      `# 预问诊报告\n\n## 主诉\n${report.chief_complaint || "未提供"}\n\n## 现病史\n${
        report.present_illness || "未提供"
      }\n\n## 过敏史\n${report.allergy_history || "无已知药物/食物过敏"}\n\n## 既往史\n${
        report.past_history || "未提供"
      }\n\n## 科室推荐\n${depts
        .map((d, i) => `${i + 1}. ${d.dept}${d.reason ? `：${d.reason}` : ""}`)
        .join("\n")}\n\n> ${report.disclaimer || DISCLAIMER}`,
    [report, depts]
  );

  const copy = async () => {
    try { await navigator.clipboard.writeText(md); } catch { /* 忽略 */ }
  };
  const download = () => {
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "pre_diagnose_report.md";
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className="space-y-3 p-4">
      <Card className="w-full">
        <Title level={5} style={{ marginTop: 0 }}>预问诊报告</Title>

        <div className="mb-4 flex flex-wrap gap-2">
          {depts.map((d, i) => (
            <Tag key={d.dept + i} color={i === 0 ? "blue" : "default"} className="py-1 px-3">
              <span className="font-semibold">{i + 1}. {d.dept}</span>
              {d.reason && <Text type="secondary" className="ml-1 text-xs">{d.reason}</Text>}
            </Tag>
          ))}
        </div>

        <div className="prose prose-sm max-w-none">
          <ReactMarkdown>{md}</ReactMarkdown>
        </div>

        <div className="mt-4 flex gap-2">
          <Button icon={<CopyOutlined />} onClick={copy}>复制报告</Button>
          <Button icon={<DownloadOutlined />} onClick={download}>导出 .md</Button>
        </div>
      </Card>

      <Paragraph className="mb-0 text-center">
        <Text type="secondary" className="text-xs">{report.disclaimer || DISCLAIMER}</Text>
      </Paragraph>
    </div>
  );
}