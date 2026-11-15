// shortcut: local demo PINs per astronaut (no auth in the API); replace with real crew auth if the console gets users.
// Override with VITE_WELLBEING_PINS='{"ast-01":"1111"}'. Unknown astronauts fall back to DEFAULT_PIN.
const DEFAULT_PIN = "0000";

const DEMO_PINS: Record<string, string> = {
  "ast-01": "1111",
  "ast-02": "2222",
  "ast-03": "3333",
  "ast-04": "4444",
};

function configuredPins(): Record<string, string> {
  try {
    return { ...DEMO_PINS, ...JSON.parse(import.meta.env.VITE_WELLBEING_PINS ?? "{}") };
  } catch {
    return DEMO_PINS;
  }
}

const PINS = configuredPins();

export const checkPin = (astronautId: string, pin: string) => (PINS[astronautId] ?? DEFAULT_PIN) === pin;
