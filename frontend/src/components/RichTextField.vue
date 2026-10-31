<template>
  <div>
    <Editor
      v-model="content"
      :extensions="extensions"
      :placeholder="placeholder"
      :editable="editable"
      :upload-function="upload"
      @change="(val) => emit('change', val)"
    >
      <EditorFixedMenu
        v-if="fixedMenu"
        :items="fullToolbar"
        class="w-full overflow-x-auto rounded-t-lg border border-b-0 border-outline-gray-2 p-1"
      />
      <EditorBubbleMenu v-if="bubbleMenu" :items="bubbleToolbar" />
      <EditorContent :class="editorClass" />
    </Editor>
  </div>
</template>

<script setup>
import {
  Editor,
  EditorContent,
  EditorFixedMenu,
  EditorBubbleMenu,
} from 'frappe-ui/editor'
import {
  buildEditorExtensions,
  fullToolbar,
  bubbleToolbar,
  uploadFile,
} from '@/components/editor/config'
import { onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  content: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  editable: { type: Boolean, default: true },
  editorClass: { type: String, default: '' },
  fixedMenu: { type: Boolean, default: false },
  bubbleMenu: { type: Boolean, default: true },
})

const emit = defineEmits(['change', 'uploading'])
let active = true
let uploads = 0
onBeforeUnmount(() => {
  active = false
})
async function upload(file) {
  uploads++
  emit('uploading', true)
  try {
    return await uploadFile(file)
  } finally {
    uploads--
    if (active) emit('uploading', uploads > 0)
  }
}

const content = ref(props.content ?? '')

watch(
  () => props.content,
  (val) => {
    content.value = val ?? ''
  },
)

const extensions = buildEditorExtensions()
</script>
