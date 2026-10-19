"use client";

import { useState } from "react";

import { CreateTaskModal } from "@/components/tasks/TaskForms";
import type { Member } from "@/lib/api";

export function CreateTaskFromCall({
  members,
  callId,
  contactId,
  contactName,
}: {
  members: Member[];
  callId: string;
  contactId: string | null;
  contactName: string | null;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="primary" onClick={() => setOpen(true)}>
        Tạo công việc
      </button>
      {open && (
        <CreateTaskModal
          members={members}
          onClose={() => setOpen(false)}
          defaults={{
            title: "Theo dõi sau cuộc gọi",
            type: "follow_up",
            callId,
            contactId: contactId ?? undefined,
            contactName: contactName ?? undefined,
          }}
        />
      )}
    </>
  );
}
