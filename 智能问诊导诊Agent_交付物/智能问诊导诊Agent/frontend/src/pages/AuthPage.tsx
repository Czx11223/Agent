import { useState } from "react";
import { Button, Card, Form, Input, Typography, message } from "antd";
import { useNavigate } from "react-router-dom";
import { login, register, setToken } from "../services/api";

const { Title, Text } = Typography;

export default function AuthPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const nav = useNavigate();

  const onFinish = async (v: { username: string; password: string }) => {
    try {
      const d =
        mode === "login"
          ? await login({ account: v.username, password: v.password })
          : await register({ username: v.username, password: v.password });
      // 兼容后端三种返回形态：{code,data:{token}} / {token} / AxiosResponse.data.token
      const raw = d as { token?: string; access_token?: string; data?: { token?: string } };
      const token = raw?.data?.token ?? raw?.token ?? raw?.access_token;
      if (!token) {
        // 取不到 token 禁止写入空串后跳转（空串为 falsy，会被路由守卫踢回登录页造成“卡住”）
        message.error("登录响应缺少 token，请重试");
        return;
      }
      setToken(token);
      message.success("登录成功");
      nav("/chat", { replace: true });
    } catch (e) {
      message.error(String(e));
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
      <Card className="w-full max-w-md">
        <Title level={4} className="text-center">{mode === "login" ? "登录" : "注册"}</Title>
        <Form onFinish={onFinish} layout="vertical">
          <Form.Item name="username" label="账号" rules={[{ required: true, message: "请输入账号" }]}>
            <Input autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: "请输入密码" }]}>
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>
            {mode === "login" ? "登录" : "注册"}
          </Button>
        </Form>
        <div
          className="mt-3 text-center text-sm"
          style={{ cursor: "pointer" }}
          onClick={() => setMode((m) => (m === "login" ? "register" : "login"))}
        >
          <Text type="secondary">{mode === "login" ? "没有账号？注册" : "已有账号？登录"}</Text>
        </div>
      </Card>
    </div>
  );
}