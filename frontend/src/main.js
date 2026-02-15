import { createApp } from 'vue';
import App from './App.vue';
import router from './router/index.js';
import './assets/styles.css';

const savedSkin = localStorage.getItem('chatSkin');
if (savedSkin) {
  document.documentElement.dataset.chatSkin = savedSkin;
}

const applyStoredAvatar = (key, cssVar) => {
  const value = localStorage.getItem(key);
  if (value) {
    document.documentElement.style.setProperty(cssVar, `url("${value}")`);
  }
};

applyStoredAvatar('chatAssistantAvatar', '--chat-assistant-avatar-image');
applyStoredAvatar('chatUserAvatar', '--chat-user-avatar-image');

const app = createApp(App);
app.use(router);
app.mount('#app');
