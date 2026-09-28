# P'achapp — app

Expo (React Native + TypeScript) client for P'achapp, targeting iOS/Android
(Expo Go) and web via `react-native-web`. See
`docs/specs/01-dev-tooling.md` at the repo root for the full toolchain spec.

## Get started

1. Install dependencies

   ```bash
   npm install
   ```

2. Start the app

   ```bash
   npm start
   ```

In the output, you'll find options to open the app in a

- [development build](https://docs.expo.dev/develop/development-builds/introduction/)
- [Android emulator](https://docs.expo.dev/workflow/android-studio-emulator/)
- [iOS simulator](https://docs.expo.dev/workflow/ios-simulator/)
- [Expo Go](https://expo.dev/go), a limited sandbox for trying out app development with Expo

Routes live in `app/` (Expo Router), non-route code in `src/` (`api-client/`,
`components/`, `screens/`, `hooks/`), tests in `tests/`.

## Scripts

- `npm run lint` — eslint
- `npm run format` / `npm run format:check` — prettier
- `npm run typecheck` — `tsc --noEmit`
- `npm test` — jest (jest-expo + Testing Library)

## Learn more

To learn more about developing your project with Expo, look at the following resources:

- [Expo documentation](https://docs.expo.dev/): Learn fundamentals, or go into advanced topics with our [guides](https://docs.expo.dev/guides).
- [Learn Expo tutorial](https://docs.expo.dev/tutorial/introduction/): Follow a step-by-step tutorial where you'll create a project that runs on Android, iOS, and the web.

## Join the community

Join our community of developers creating universal apps.

- [Expo on GitHub](https://github.com/expo/expo): View our open source platform and contribute.
- [Discord community](https://chat.expo.dev): Chat with Expo users and ask questions.
