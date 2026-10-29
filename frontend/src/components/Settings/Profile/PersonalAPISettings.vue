<template>
  <SettingsLayoutBase :title="__('Personal API access')">
    <template #content>
      <Button
        :label="__('Back to profile')"
        @click="emit('updateStep', 'profile-settings')"
      />
      <p class="mt-5 text-p-base text-ink-gray-6">
        {{
          __(
            'Your API credentials have the same access as your CRM account. Keep them private.',
          )
        }}
      </p>
      <p v-if="loading" class="mt-4" role="status">
        {{ __('Loading API settings…') }}
      </p>
      <template v-else-if="loaded">
        <p class="mt-4" role="status">
          {{
            configured
              ? __('You already have API credentials.')
              : __('You have not generated API credentials yet.')
          }}
        </p>
        <label v-if="configured" class="mt-4 flex items-start gap-2 text-p-sm">
          <input
            v-model="confirmReplace"
            type="checkbox"
            :disabled="generating"
          />
          {{
            __(
              'Replace my API secret. Existing integrations will need the new secret.',
            )
          }}
        </label>
        <Button
          class="mt-4"
          variant="solid"
          :label="
            configured
              ? __('Replace API secret')
              : __('Generate API credentials')
          "
          :loading="generating"
          :disabled="generating || (configured && !confirmReplace)"
          @click="generate"
        />
      </template>
      <div v-if="credentials" class="mt-6 flex max-w-lg flex-col gap-4">
        <p class="text-p-sm text-ink-gray-6">
          {{
            __(
              'Copy these credentials to your password manager. The secret is shown only here and will be cleared when you leave this page.',
            )
          }}
        </p>
        <label
          v-for="field in fields"
          :key="field.key"
          class="flex flex-col gap-2 text-base-medium"
        >
          {{ field.label }}
          <input
            class="form-input rounded border border-outline-gray-2"
            :type="revealed ? 'text' : 'password'"
            :value="credentials[field.key]"
            readonly
            autocomplete="off"
          />
          <Button :label="field.copyLabel" @click="copy(field.key)" />
        </label>
        <Button
          :label="revealed ? __('Hide credentials') : __('Reveal credentials')"
          @click="revealed = !revealed"
        />
      </div>
      <p v-if="notice" role="status" class="mt-4">{{ notice }}</p>
      <p v-if="error" role="alert" class="mt-4 text-ink-red-4">{{ error }}</p>
    </template>
  </SettingsLayoutBase>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Button, call } from 'frappe-ui'
import SettingsLayoutBase from '@/components/Layouts/SettingsLayoutBase.vue'

const emit = defineEmits(['updateStep'])
const configured = ref(false)
const loading = ref(true)
const loaded = ref(false)
const generating = ref(false)
const confirmReplace = ref(false)
const credentials = ref(null)
const revealed = ref(false)
const error = ref('')
const notice = ref('')
const fields = [
  { key: 'api_key', label: __('API key'), copyLabel: __('Copy API key') },
  {
    key: 'api_secret',
    label: __('API secret'),
    copyLabel: __('Copy API secret'),
  },
]
let active = true
onBeforeUnmount(() => {
  active = false
  credentials.value = null
})
onMounted(async () => {
  try {
    const data = await call('crm.api.personal_settings.get_personal_settings')
    if (active) {
      configured.value = data.api_configured
      loaded.value = true
    }
  } catch {
    if (active) error.value = __('Could not load your API settings. Try again.')
  } finally {
    if (active) loading.value = false
  }
})
async function generate() {
  if (generating.value || (configured.value && !confirmReplace.value)) return
  generating.value = true
  error.value = ''
  notice.value = ''
  credentials.value = null
  revealed.value = false
  try {
    const result = await call(
      'crm.api.personal_settings.generate_personal_api_keys',
      { confirm_replace: confirmReplace.value },
    )
    if (active) {
      credentials.value = result
      configured.value = true
      confirmReplace.value = false
    }
  } catch {
    if (active)
      error.value = __(
        'Could not generate credentials. If the connection was interrupted, the secret may have changed. Confirm replacement to generate a fresh secret.',
      )
    try {
      const status = await call(
        'crm.api.personal_settings.get_personal_settings',
      )
      if (active) configured.value = status.api_configured
    } catch {
      if (active) loaded.value = false
    }
  } finally {
    if (active) generating.value = false
  }
}
async function copy(key) {
  if (!credentials.value) return
  try {
    await navigator.clipboard.writeText(credentials.value[key])
    if (active) notice.value = __('Copied to clipboard.')
  } catch {
    if (active)
      error.value = __(
        'Clipboard access was blocked. Reveal the credentials and copy them manually.',
      )
  }
}
</script>
