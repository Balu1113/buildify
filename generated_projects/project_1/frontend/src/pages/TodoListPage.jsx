import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { todoApi } from '../api/todos';
import Layout from '../components/layout/Layout';
import TodoCard from '../components/todos/TodoCard';
import TodoFilters from '../components/todos/TodoFilters';
import TodoPagination from '../components/todos/TodoPagination';
import TodoForm from '../components/todos/TodoForm';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ErrorMessage from '../components/ui/ErrorMessage';
import { Plus, CheckCircle } from 'lucide-react';
import Button from '../components/ui/Button';

const TodoListPage = () => {
  const [todos, setTodos] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingTodo, setEditingTodo] = useState(null);
  const [searchParams] = useSearchParams();
  
  const pageSize = 10;

  const fetchTodos = async () => {
    setLoading(true);
    try {
      const params = Object.fromEntries(searchParams.entries());
      const res = await todoApi.list(params);
      setTodos(res.data.results);
      setTotalCount(res.data.count);
    } catch (err) {
      setError("Failed to fetch todos.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTodos();
  }, [searchParams]);

  const handleToggleStatus = async (todo) => {
    const newStatus = todo.status === 'completed' ? 'pending' : 'completed';
    try {
      await todoApi.update(todo.id, { ...todo, status: newStatus });
      fetchTodos();
    } catch (err) {
      setError("Failed to update status");
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Are you sure you want to delete this task?")) return;
    try {
      await todoApi.delete(id);
      fetchTodos();
    } catch (err) {
      setError("Failed to delete task");
    }
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">My Tasks</h1>
            <p className="text-gray-600">Manage and organize your daily to-dos.</p>
          </div>
          <Button onClick={() => { setEditingTodo(null); setIsModalOpen(true); }}>
            <Plus className="w-5 h-5 mr-2" /> New Task
          </Button>
        </div>

        <TodoFilters />

        {error && <ErrorMessage message={error} />}

        {loading ? (
          <LoadingSpinner className="my-12" />
        ) : (
          <>
            {todos.length === 0 ? (
              <div className="text-center py-20 bg-white rounded-xl border border-dashed border-gray-300">
                <CheckCircle className="w-16 h-16 text-gray-300 mx-auto mb-4" />
                <h3 className="text-xl font-medium text-gray-900">No tasks found</h3>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {todos.map((todo) => (
                  <TodoCard
                    key={todo.id}
                    todo={todo}
                    onToggleStatus={handleToggleStatus}
                    onEdit={(t) => { setEditingTodo(t); setIsModalOpen(true); }}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            )}
            <TodoPagination totalCount={totalCount} pageSize={pageSize} />
          </>
        )}
      </div>

      {isModalOpen && (
        <TodoForm 
          initialData={editingTodo} 
          onClose={() => { setIsModalOpen(false); fetchTodos(); }} 
        />
      )}
    </Layout>
  );
};

export default TodoListPage;