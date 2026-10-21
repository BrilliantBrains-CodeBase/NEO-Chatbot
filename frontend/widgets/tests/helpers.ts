import type { Locator } from '@playwright/test';

// The panel opens with a short zoom animation. Sizes and positions measured while it runs are scaled
// and change between two measurements, so wait for it to finish before measuring anything.
// A cancelled animation rejects its "finished" promise (AbortError); that also means it is over.
export async function settled(panel: Locator): Promise<void> {
  await panel.evaluate((el) =>
    Promise.all(el.getAnimations({ subtree: true }).map((a) => a.finished.catch(() => undefined))),
  );
}
