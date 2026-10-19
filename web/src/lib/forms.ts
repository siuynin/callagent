"use client";

import { type FormEvent, startTransition } from "react";

/**
 * Submit a form to a useActionState dispatcher WITHOUT React's automatic form reset.
 * `<form action={fn}>` resets every field after the action, even when the server rejected the input,
 * which throws away what the user chose. Use: <form onSubmit={submitTo(action)}>.
 */
export function submitTo(dispatch: (data: FormData) => void) {
  return (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    startTransition(() => dispatch(data));
  };
}
