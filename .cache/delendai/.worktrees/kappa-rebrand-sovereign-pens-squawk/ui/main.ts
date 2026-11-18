// Entry point: mount the Svelte 5 Squawk app.
// (Imports the compiler output in ./dist/; see ui/build.ts.)
import { mount } from "svelte";
import App from "./dist/App.js";

const root = document.getElementById("root");
if (!root) throw new Error("no #root element");
mount(App, { target: root });
