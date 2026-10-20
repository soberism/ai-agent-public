import Input from "@rc-component/input";
import { Select } from "../../shared/Select";
import { useState } from "react";

type Submit = (path: string, body: Record<string, string | null>) => Promise<boolean>;

export function InviteForm({ householdId, submit }: { householdId: string; submit: Submit }) {
  const [email, setEmail] = useState("");
  return (
    <form
      className="compact-form family-invite-form"
      onSubmit={(event) => {
        event.preventDefault();
        void submit(`/households/${householdId}/invitations`, { email, role: "member" }).then(
          (saved) => saved && setEmail(""),
        );
      }}
    >
      <label>
        邀请邮箱
        <Input
          placeholder="填写对方的邮箱"
          autoComplete="email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </label>
      <p className="muted small">加入后成为家庭成员</p>
      <button className="primary">发出站内邀请</button>
    </form>
  );
}

export function ProfileForm({ householdId, submit }: { householdId: string; submit: Submit }) {
  const [name, setName] = useState("");
  const [relationship, setRelationship] = useState("child");
  return (
    <form
      className="compact-form"
      onSubmit={(event) => {
        event.preventDefault();
        void submit(`/households/${householdId}/profiles`, {
          name,
          relationship,
          birth_date: null,
        }).then((saved) => saved && setName(""));
      }}
    >
      <label>
        姓名或称呼
        <Input
          autoComplete="off"
          required
          maxLength={60}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        关系
        <Select value={relationship} onChange={(e) => setRelationship(e.target.value)}>
          <option value="child">孩子</option>
          <option value="parent">长辈</option>
          <option value="other">其他</option>
        </Select>
      </label>
      <button>添加托管档案</button>
    </form>
  );
}

export function PetForm({ householdId, submit }: { householdId: string; submit: Submit }) {
  const [name, setName] = useState("");
  const [species, setSpecies] = useState("dog");
  return (
    <form
      className="compact-form"
      onSubmit={(event) => {
        event.preventDefault();
        void submit(`/households/${householdId}/pets`, { name, species, breed: null }).then(
          (saved) => saved && setName(""),
        );
      }}
    >
      <label>
        宠物名
        <Input
          autoComplete="off"
          required
          maxLength={60}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        类型
        <Select value={species} onChange={(e) => setSpecies(e.target.value)}>
          <option value="dog">狗</option>
          <option value="cat">猫</option>
          <option value="other">其他</option>
        </Select>
      </label>
      <button>添加宠物</button>
    </form>
  );
}
