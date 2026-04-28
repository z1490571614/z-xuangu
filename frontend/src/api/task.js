import api from './index'

export const getTasks = () => {
  return api.get('/tasks')
}

export const createTask = (data) => {
  return api.post('/tasks', data)
}

export const updateTask = (id, data) => {
  return api.put(`/tasks/${id}`, data)
}

export const deleteTask = (id) => {
  return api.delete(`/tasks/${id}`)
}
