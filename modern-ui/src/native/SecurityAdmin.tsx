import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api/client'

type Row = Record<string, any>

type Topic = { topic: string; template: string }

const blankUser: Row = {
  username: '',
  password: '',
  email: '',
  first_name: '',
  last_name: '',
  is_active: true,
  roles: ['scenescape-viewer'],
  scenes: [],
  acls: [],
}

const usernameOf = (row: Row) => String(row.username || '')

export default function SecurityAdmin({ scenes }: { scenes: Row[] }) {
  const [users, setUsers] = useState<Row[]>([])
  const [topics, setTopics] = useState<Topic[]>([])
  const [services, setServices] = useState<Row[]>([])
  const [selected, setSelected] = useState<Row | null>(null)
  const [draft, setDraft] = useState<Row>({ ...blankUser })
  const [query, setQuery] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => {
    void apiFetch<Row[]>('/api/v2/users').then(setUsers).catch((e) => setError(String(e)))
    void apiFetch<Topic[]>('/api/v2/security/topics').then(setTopics).catch((e) => setError(String(e)))
    void apiFetch<Row[]>('/api/v2/security/services').then(setServices).catch((e) => setError(String(e)))
  }
  useEffect(load, [])

  const filtered = useMemo(
    () => users.filter((row) => JSON.stringify(row).toLowerCase().includes(query.toLowerCase())),
    [users, query],
  )

  const open = (row: Row | null) => {
    setSelected(row)
    setDraft(row ? {
      ...blankUser,
      ...row,
      password: '',
      roles: Array.isArray(row.roles) ? [...row.roles] : [],
      scenes: Array.isArray(row.scenes) ? [...row.scenes] : [],
      acls: Array.isArray(row.acls) ? row.acls.map((acl: Row) => ({ ...acl })) : [],
    } : { ...blankUser, roles: ['scenescape-viewer'], scenes: [], acls: [] })
    setMessage('')
    setError('')
  }

  const field = (key: string, value: unknown) => setDraft((old) => ({ ...old, [key]: value }))
  const hasRole = (role: string) => Array.isArray(draft.roles) && draft.roles.includes(role)
  const toggleRole = (role: string, enabled: boolean) => {
    const current = Array.isArray(draft.roles) ? draft.roles.map(String) : []
    field('roles', enabled ? Array.from(new Set([...current, role])) : current.filter((item) => item !== role))
  }
  const hasScene = (uid: string) => Array.isArray(draft.scenes) && draft.scenes.includes(uid)
  const toggleScene = (uid: string, enabled: boolean) => {
    const current = Array.isArray(draft.scenes) ? draft.scenes.map(String) : []
    field('scenes', enabled ? Array.from(new Set([...current, uid])) : current.filter((item) => item !== uid))
  }

  const updateAcl = (index: number, key: 'topic' | 'access', value: string | number) => {
    const acls: Row[] = Array.isArray(draft.acls) ? draft.acls.map((item: Row) => ({ ...item })) : []
    acls[index] = { ...acls[index], [key]: value }
    field('acls', acls)
  }
  const addAcl = () => {
    const acls: Row[] = Array.isArray(draft.acls) ? [...draft.acls] : []
    acls.push({ topic: topics[0]?.topic || 'DATA_SCENE', access: 1 })
    field('acls', acls)
  }
  const removeAcl = (index: number) => {
    const acls: Row[] = Array.isArray(draft.acls) ? draft.acls.filter((_: Row, i: number) => i !== index) : []
    field('acls', acls)
  }

  const save = async () => {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const payload: Row = {
        username: String(draft.username || '').trim(),
        email: String(draft.email || ''),
        first_name: String(draft.first_name || ''),
        last_name: String(draft.last_name || ''),
        is_active: Boolean(draft.is_active),
        roles: Array.isArray(draft.roles) ? draft.roles : [],
        scenes: Array.isArray(draft.scenes) ? draft.scenes : [],
        acls: Array.isArray(draft.acls) ? draft.acls : [],
      }
      if (String(draft.password || '')) payload.password = String(draft.password)
      if (!selected && !payload.password) throw new Error('A password is required when creating a user.')
      if (selected) delete payload.username
      const saved = selected
        ? await apiFetch<Row>(`/api/v2/users/${encodeURIComponent(usernameOf(selected))}`, { method: 'PUT', body: JSON.stringify(payload) })
        : await apiFetch<Row>('/api/v2/users', { method: 'POST', body: JSON.stringify(payload) })
      setSelected(saved)
      setDraft({ ...blankUser, ...saved, password: '' })
      setMessage('Keycloak user, roles, scene scopes and MQTT ACLs saved.')
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!selected || !window.confirm(`Delete Keycloak user ${usernameOf(selected)}?`)) return
    setBusy(true)
    setError('')
    try {
      await apiFetch(`/api/v2/users/${encodeURIComponent(usernameOf(selected))}`, { method: 'DELETE' })
      open(null)
      setSelected(null)
      setMessage('User deleted from Keycloak.')
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  return <div className="security-admin-layout">
    <section className="panel security-user-list">
      <div className="panel-title"><div><h2>Identity</h2><p>Keycloak is the source of truth.</p></div><button className="btn btn-primary" onClick={() => open(null)}>New user</button></div>
      <div className="toolbar camera-toolbar"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search users"/><span className="muted">{filtered.length} users</span></div>
      <div className="scene-list">{filtered.map((row) => <button key={usernameOf(row)} className={selected && usernameOf(selected) === usernameOf(row) ? 'scene-config-row active' : 'scene-config-row'} onClick={() => open(row)}>
        <span><b>{usernameOf(row)}</b><small>{row.email || row.uid}</small></span>
        <span><small>{Array.isArray(row.roles) ? row.roles.join(', ') : 'authenticated'} · {row.is_active ? 'active' : 'disabled'}</small></span>
      </button>)}{!filtered.length && <div className="table-empty">No Keycloak users found.</div>}</div>
      <div className="service-identity-list"><h3>Service identities</h3>{services.map((service) => <div key={usernameOf(service)}><span><b>{usernameOf(service)}</b><small>{String(service.service_type || 'service')} · mounted secret</small></span><span>{Array.isArray(service.acls) ? service.acls.length : 0} ACLs</span></div>)}{!services.length && <div className="table-empty">No mounted service identities.</div>}</div>
    </section>

    <section className="panel security-user-editor">
      <div className="panel-title"><div><h2>{selected ? `Manage ${usernameOf(selected)}` : 'Create user'}</h2><p>Roles authorize API operations; scene scopes constrain visible scenes; MQTT ACLs authorize broker topics.</p></div></div>
      {message && <div className="notice-box security-message">{message}</div>}
      {error && <div className="error-box security-message">{error}</div>}
      <div className="scene-form-grid security-profile">
        <label>Username<input value={String(draft.username || '')} disabled={Boolean(selected)} onChange={(e) => field('username', e.target.value)}/></label>
        <label>{selected ? 'New password' : 'Password'}<input type="password" value={String(draft.password || '')} onChange={(e) => field('password', e.target.value)} placeholder={selected ? 'Leave blank to keep current' : ''}/></label>
        <label>Email<input value={String(draft.email || '')} onChange={(e) => field('email', e.target.value)}/></label>
        <label className="checkbox-label"><input type="checkbox" checked={Boolean(draft.is_active)} onChange={(e) => field('is_active', e.target.checked)}/>Active</label>
        <label>First name<input value={String(draft.first_name || '')} onChange={(e) => field('first_name', e.target.value)}/></label>
        <label>Last name<input value={String(draft.last_name || '')} onChange={(e) => field('last_name', e.target.value)}/></label>
      </div>

      <div className="security-columns">
        <div className="scene-subsection">
          <h3>Realm roles</h3>
          <div className="security-check-list">
            <label><input type="checkbox" checked={hasRole('scenescape-viewer')} onChange={(e) => toggleRole('scenescape-viewer', e.target.checked)}/><span><b>Viewer</b><small>Read operational data and authorized scenes.</small></span></label>
            <label><input type="checkbox" checked={hasRole('scenescape-admin')} onChange={(e) => toggleRole('scenescape-admin', e.target.checked)}/><span><b>Administrator</b><small>Configuration and identity administration.</small></span></label>
          </div>
        </div>
        <div className="scene-subsection">
          <h3>Scene scopes</h3>
          <div className="security-check-list">
            <label><input type="checkbox" checked={hasScene('*')} onChange={(e) => toggleScene('*', e.target.checked)}/><span><b>All scenes</b><small>*</small></span></label>
            {scenes.map((scene) => <label key={String(scene.uid)}><input type="checkbox" disabled={hasScene('*')} checked={hasScene(String(scene.uid)) || hasScene('*')} onChange={(e) => toggleScene(String(scene.uid), e.target.checked)}/><span><b>{String(scene.name || scene.uid)}</b><small>{String(scene.uid)}</small></span></label>)}
          </div>
        </div>
      </div>

      <div className="scene-subsection">
        <div className="security-acl-title"><div><h3>MQTT topic ACLs</h3><p>Compatibility policy consumed by <code>/api/v1/aclcheck</code>.</p></div><button className="btn" onClick={addAcl}>Add ACL</button></div>
        <div className="security-acl-table">
          {(Array.isArray(draft.acls) ? draft.acls : []).map((acl: Row, index: number) => <div key={index}>
            <select value={String(acl.topic || '')} onChange={(e) => updateAcl(index, 'topic', e.target.value)}>{topics.map((topic) => <option key={topic.topic} value={topic.topic}>{topic.topic}</option>)}</select>
            <select value={Number(acl.access ?? 0)} onChange={(e) => updateAcl(index, 'access', Number(e.target.value))}>
              <option value={0}>No access</option><option value={1}>Read</option><option value={2}>Write</option><option value={3}>Read + write</option>
            </select>
            <code>{topics.find((topic) => topic.topic === acl.topic)?.template || ''}</code>
            <button className="text-button" onClick={() => removeAcl(index)}>Remove</button>
          </div>)}
          {(!Array.isArray(draft.acls) || !draft.acls.length) && <div className="table-empty">No MQTT ACLs. Non-admin broker access is denied.</div>}
        </div>
      </div>
      <div className="editor-actions camera-save-actions">{selected && <button className="btn danger-button" disabled={busy} onClick={() => void remove()}>Delete user</button>}<button className="btn btn-primary" disabled={busy} onClick={() => void save()}>{busy ? 'Working…' : 'Save identity'}</button></div>
    </section>
  </div>
}
