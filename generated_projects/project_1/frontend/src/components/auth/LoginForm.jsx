import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { authApi } from '../../api/auth';
import Input from '../ui/Input';
import Button from '../ui/Button';
import ErrorMessage from '../ui/ErrorMessage';
import { Lock, User } from 'lucide-react';

const LoginForm = () => {
  const [credentials, setCredentials] = useState({ username: '', password: '' });
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrors({});
    setLoading(true);

    try {
      const response = await authApi.login(credentials);
      await login(response.data.user, response.data.access, response.data.refresh);
      navigate('/dashboard');
    } catch (err) {
      setErrors({ general: err.response?.data?.detail || 'Invalid username or password' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md w-full mx-auto bg-white p-8 rounded-xl shadow-lg">
      <div className="text-center mb-8">
        <h2 className="text-3xl font-bold text-gray-900">Welcome Back</h2>
        <p className="text-gray-500 mt-2">Please enter your details to sign in</p>
      </div>

      {errors.general && <ErrorMessage message={errors.general} />}

      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <Input
            label="Username"
            type="text"
            required
            value={credentials.username}
            onChange={(e) => setCredentials({ ...credentials, username: e.target.value })}
            icon={<User className="w-5 h-5 text-gray-400" />}
          />
        </div>
        <div>
          <Input
            label="Password"
            type="password"
            required
            value={credentials.password}
            onChange={(e) => setCredentials({ ...credentials, password: e.target.value })}
            icon={<Lock className="w-5 h-5 text-gray-400" />}
          />
        </div>

        <Button type="submit" className="w-full py-3" isLoading={loading}>
          Sign In
        </Button>
      </form>

      <div className="mt-6 text-center">
        <p className="text-sm text-gray-600">
          Don't have an account?{' '}
          <Link to="/register" className="font-medium text-blue-600 hover:text-blue-500">
            Register for free
          </Link>
        </p>
      </div>
    </div>
  );
};

export default LoginForm;