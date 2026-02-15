<template>
  <div class="modal-mask" @click.self="$emit('close')">
    <div class="modal-card card">
      <slot />
      <div class="actions" style="justify-content: flex-end;">
        <button class="ghost" @click="$emit('close')">取消</button>
      </div>
    </div>
  </div>
</template>

<script setup>
defineEmits(['close']);
</script>
