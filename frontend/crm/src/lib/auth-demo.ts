// TEMPORARY (sub-step 1, screens only): stands in for the real sign-in until it is connected to Supabase.
// It behaves like the approved design's demo: a password shorter than 8 characters is "incorrect". Nothing
// is sent anywhere. Removed when sign-in is connected.

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function demoSignIn(_email: string, password: string): Promise<{ ok: boolean }> {
  await wait(700);
  return { ok: password.length >= 8 };
}
